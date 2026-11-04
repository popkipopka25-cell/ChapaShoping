"""API Telegram Mini App: авторизация, профиль, заказы. Telegram ID берётся только из проверенного initData."""
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ORDER_STATUS_RU, Order, OrderItem, OrderStatus, OrderStatusHistory, Product, User
from app.tg_auth import InitDataError, verify_init_data

router = APIRouter(prefix="/api", tags=["miniapp"])
ROBLOX_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MAX_QTY, MAX_LINES = 99, 50

# Простое ограничение частоты создания заказов: 5 в минуту на пользователя.
_hits: dict[int, deque] = defaultdict(deque)


def _rate_limit(tg_id: int, limit: int = 5, window: int = 60):
    q, t = _hits[tg_id], time.monotonic()
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Слишком много заказов, подождите минуту")
    q.append(t)


def current_user(db: Session = Depends(get_db),
                 x_telegram_init_data: str = Header(default="")) -> User:
    try:
        tg = verify_init_data(x_telegram_init_data, get_settings().bot_token)
    except InitDataError:
        raise HTTPException(401, "Откройте магазин через Telegram")
    user = db.scalar(select(User).where(User.telegram_id == tg["id"]))
    if user is None:
        user = User(telegram_id=tg["id"])
        db.add(user)
    user.username = (tg.get("username") or None)
    user.first_name = (str(tg.get("first_name") or "")[:128]) or None
    db.commit()
    return user


def _order_out(o: Order) -> dict:
    return {
        "id": o.id, "number": o.number, "created_at": o.created_at.isoformat(),
        "roblox_username": o.roblox_username, "total_stars": o.total_stars,
        "payment_status": o.payment_status.value, "status": o.status.value,
        "status_ru": ORDER_STATUS_RU[o.status.value], "server_link": o.server_link,
        "items": [{"name": i.product_name, "price_stars": i.price_stars, "quantity": i.quantity,
                   "subtotal": i.price_stars * i.quantity} for i in o.items],
        "history": [{"status": h.new_status, "status_ru": ORDER_STATUS_RU.get(h.new_status, h.new_status),
                     "comment": h.comment if h.new_status == "rejected" else None,
                     "at": h.created_at.isoformat()} for h in sorted(o.history, key=lambda x: x.id)],
        "has_receipt": o.payment_status.value in ("paid", "refunded"),
    }


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = len(db.scalars(select(Order.id).where(Order.user_id == user.id)).all())
    return {"telegram_id": user.telegram_id, "username": user.username, "first_name": user.first_name,
            "roblox_username": user.roblox_username, "orders_count": count}


class RobloxIn(BaseModel):
    roblox_username: str = Field(max_length=20)


@router.put("/me/roblox")
def set_roblox(body: RobloxIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    nick = body.roblox_username.strip()
    if not ROBLOX_RE.match(nick):
        raise HTTPException(422, "3–20 символов: латиница, цифры и _")
    user.roblox_username = nick
    db.commit()
    return {"roblox_username": nick}


@router.get("/orders")
def my_orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    orders = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(100)).all()
    return [_order_out(o) for o in orders]


@router.get("/orders/{order_id}")
def my_order(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if o is None or o.user_id != user.id:   # чужие заказы не видны
        raise HTTPException(404, "Заказ не найден")
    return _order_out(o)


class LineIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=MAX_QTY)


class OrderIn(BaseModel):
    items: list[LineIn] = Field(min_length=1, max_length=MAX_LINES)
    roblox_username: str = Field(max_length=20)


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    nick = body.roblox_username.strip()
    if not ROBLOX_RE.match(nick):
        raise HTTPException(422, "Неверный Roblox username")
    _rate_limit(user.telegram_id)
    merged: dict[int, int] = {}
    for l in body.items:
        merged[l.product_id] = min(MAX_QTY, merged.get(l.product_id, 0) + l.quantity)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(merged))).all()}
    items, total = [], 0
    for pid, qty in merged.items():
        p = products.get(pid)
        if p is None or p.is_hidden or not p.is_available:
            raise HTTPException(409, f"Товар {pid} недоступен — обновите корзину")
        items.append(OrderItem(product_id=p.id, product_name=p.name, price_stars=p.price_stars, quantity=qty))
        total += p.price_stars * qty
    o = Order(user_id=user.id, telegram_id=user.telegram_id, roblox_username=nick, total_stars=total,
              items=items, history=[OrderStatusHistory(old_status=None, new_status=OrderStatus.awaiting_payment.value,
                                                        changed_by="customer")])
    user.roblox_username = nick
    db.add(o)
    db.commit()   # номер заказа = автоинкремент БД, конфликтов при одновременном создании нет
    db.refresh(o)
    from bot import notify
    try:
        notify.order_created(db, o)
    except Exception:
        pass
    return _order_out(o)


@router.post("/orders/{order_id}/invoice")
def order_invoice(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Создаёт настоящий invoice Telegram Stars. Оплата засчитывается только по successful_payment."""
    from bot import payments
    from bot.telegram import TelegramError
    o = db.get(Order, order_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if not payments.can_pay(o):
        raise HTTPException(409, "Заказ уже оплачен или отменён")
    try:
        link = payments.create_invoice_link(o)
    except TelegramError:
        raise HTTPException(502, "Telegram не создал счёт, попробуйте позже")
    if not link:
        raise HTTPException(503, "Тестовый режим: оплата не подключена")
    return {"invoice_link": link}


_receipt_hits: dict[int, deque] = defaultdict(deque)


@router.post("/orders/{order_id}/receipt")
def send_my_receipt(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Покупатель просит прислать PDF-чек в чат с ботом (не чаще 3 раз в минуту)."""
    o = db.get(Order, order_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(404, "Заказ не найден")
    if o.payment_status.value not in ("paid", "refunded"):
        raise HTTPException(400, "Чек появится после оплаты")
    q, t = _receipt_hits[user.id], time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= 3:
        raise HTTPException(429, "Подождите минуту")
    q.append(t)
    from bot import notify
    return {"ok": True, "sent": notify.receipt(db, o)}
