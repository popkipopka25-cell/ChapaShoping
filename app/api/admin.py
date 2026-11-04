"""Панель владельца (Этап 6): вход, заказы, товары, покупатели, настройки, журнал."""
import hmac
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import (ORDER_STATUS_RU, Admin, AuditLog, Category, Order, OrderItem,
                        OrderStatus, OrderStatusHistory, Payment, Product, Setting, User)
from app.security import (COOKIE, SESSION_TTL, check_session, csrf_for, hash_password,
                          make_session, parse_session, verify_password)

router = APIRouter(prefix="/admin/api", tags=["admin"])

# Ограничение попыток входа: 5 неудачных за 10 минут с одного адреса.
_fails: dict[str, deque] = defaultdict(deque)
FAIL_LIMIT, FAIL_WINDOW = 5, 600

# Ключи, которые нельзя менять через панель (секреты живут только в переменных окружения).
EDITABLE_SETTINGS_EXCLUDE = set()


def ensure_owner(db: Session) -> None:
    """Создаёт владельца из ADMIN_USERNAME/ADMIN_PASSWORD, если владельца ещё нет."""
    s = get_settings()
    if not s.admin_password or db.scalar(select(Admin).limit(1)) is not None:
        return
    db.add(Admin(username=s.admin_username, password_hash=hash_password(s.admin_password)))
    db.commit()


def audit(db: Session, actor: str, action: str, entity: str | None = None,
          entity_id=None, details: dict | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity,
                    entity_id=None if entity_id is None else str(entity_id), details=details))


def current_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    token = request.cookies.get(COOKIE)
    parsed = parse_session(token)
    admin = db.get(Admin, parsed[0]) if parsed else None
    if admin is None or not check_session(token, admin.password_hash):
        raise HTTPException(401, "Нужен вход")
    if request.method not in ("GET", "HEAD"):
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, csrf_for(token)):
            raise HTTPException(403, "Неверный CSRF-токен")
    return admin


# ---------- Вход ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _set_cookie(resp: Response, token: str, request: Request):
    resp.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", path="/admin")


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    q, t = _fails[ip], time.monotonic()
    while q and t - q[0] > FAIL_WINDOW:
        q.popleft()
    if len(q) >= FAIL_LIMIT:
        raise HTTPException(429, "Слишком много попыток. Подождите 10 минут.")
    admin = db.scalar(select(Admin).where(Admin.username == body.username))
    if admin is None or not verify_password(body.password, admin.password_hash):
        q.append(t)
        audit(db, body.username[:64], "login_failed", details={"ip": ip})
        db.commit()
        raise HTTPException(401, "Неверный логин или пароль")
    q.clear()
    token, csrf = make_session(admin.id, admin.password_hash)
    _set_cookie(response, token, request)
    audit(db, admin.username, "login", details={"ip": ip})
    db.commit()
    return {"username": admin.username, "csrf": csrf}


@router.post("/logout")
def logout(response: Response, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    response.delete_cookie(COOKIE, path="/admin")
    audit(db, admin.username, "logout")
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(request: Request, admin: Admin = Depends(current_admin)):
    return {"username": admin.username, "csrf": csrf_for(request.cookies.get(COOKIE))}


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, response: Response,
                    admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, admin.password_hash):
        raise HTTPException(400, "Старый пароль неверный")
    admin.password_hash = hash_password(body.new_password)
    audit(db, admin.username, "password_changed")
    db.commit()
    token, csrf = make_session(admin.id, admin.password_hash)
    _set_cookie(response, token, request)
    return {"ok": True, "csrf": csrf}


# ---------- Сводка ----------
@router.get("/stats")
def stats(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    revenue = db.scalar(select(func.coalesce(func.sum(Payment.amount_stars), 0)).where(Payment.status == "succeeded"))
    return {
        "orders_total": sum(by_status.values()),
        "by_status": {k.value if hasattr(k, "value") else k: v for k, v in by_status.items()},
        "revenue_stars": revenue,
        "customers": db.scalar(select(func.count(User.id))),
        "products": db.scalar(select(func.count(Product.id))),
    }


# ---------- Заказы ----------
def order_dict(o: Order, full: bool = False) -> dict:
    d = {"id": o.id, "number": o.number, "created_at": o.created_at.isoformat(),
         "telegram_id": o.telegram_id, "roblox_username": o.roblox_username,
         "total_stars": o.total_stars, "payment_status": o.payment_status.value,
         "status": o.status.value, "status_ru": ORDER_STATUS_RU[o.status.value],
         "server_link": o.server_link}
    if full:
        d["items"] = [{"product_id": i.product_id, "name": i.product_name, "price_stars": i.price_stars,
                       "quantity": i.quantity, "subtotal": i.price_stars * i.quantity} for i in o.items]
        d["history"] = [{"old": h.old_status, "new": h.new_status,
                         "new_ru": ORDER_STATUS_RU.get(h.new_status, h.new_status),
                         "by": h.changed_by, "comment": h.comment, "at": h.created_at.isoformat()}
                        for h in sorted(o.history, key=lambda x: x.id)]
    return d


@router.get("/orders")
def orders(_: Admin = Depends(current_admin), db: Session = Depends(get_db),
           status: str | None = None, q: str | None = None, limit: int = 100, offset: int = 0):
    stmt = select(Order)
    if status:
        if status not in ORDER_STATUS_RU:
            raise HTTPException(400, "Неизвестный статус")
        stmt = stmt.where(Order.status == OrderStatus(status))
    if q:
        q = q.strip()[:64]
        conds = [Order.roblox_username.ilike(f"%{q}%")]
        if q.lstrip("#").isdigit():
            conds += [Order.id == int(q.lstrip("#")), Order.telegram_id == int(q.lstrip("#"))]
        stmt = stmt.where(or_(*conds))
    rows = db.scalars(stmt.order_by(Order.id.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))).all()
    return [order_dict(o) for o in rows]


def _get_order(db: Session, oid: int) -> Order:
    o = db.get(Order, oid)
    if o is None:
        raise HTTPException(404, "Заказ не найден")
    return o


@router.get("/orders/{oid}")
def order_detail(oid: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    d = order_dict(o, full=True)
    u = db.get(User, o.user_id)
    d["customer"] = {"id": u.id, "username": u.username, "first_name": u.first_name} if u else None
    d["payments"] = [{"charge_id": p.telegram_payment_charge_id, "amount": p.amount_stars, "status": p.status,
                      "at": p.created_at.isoformat()}
                     for p in db.scalars(select(Payment).where(Payment.order_id == o.id))]
    return d


# Разрешённые переходы статусов из панели. Оплату ставит только Telegram.
TRANSITIONS = {
    "awaiting_payment": {"rejected"},
    "paid": {"processing", "awaiting_delivery", "delivered", "rejected"},
    "processing": {"awaiting_delivery", "delivered", "rejected"},
    "awaiting_delivery": {"processing", "delivered", "rejected"},
    "delivered": set(),
    "rejected": set(),
    "refunded": set(),
}


class StatusIn(BaseModel):
    status: str
    comment: str | None = Field(None, max_length=500)
    notify: bool = True


@router.post("/orders/{oid}/status")
def set_status(oid: int, body: StatusIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    old = o.status.value
    if body.status not in TRANSITIONS.get(old, set()):
        raise HTTPException(400, f"Нельзя сменить «{ORDER_STATUS_RU[old]}» на «{ORDER_STATUS_RU.get(body.status, body.status)}»")
    o.history.append(OrderStatusHistory(old_status=old, new_status=body.status,
                                        changed_by=admin.username, comment=body.comment))
    o.status = OrderStatus(body.status)
    audit(db, admin.username, "order_status", "order", o.id, {"from": old, "to": body.status})
    db.commit()
    sent = False
    if body.notify:
        from bot import notify
        if body.status == "rejected":
            sent = notify.rejected(db, o, body.comment)
        elif body.status == "delivered":
            sent = notify.delivered(db, o)
            notify.receipt(db, o)  # чек отправляется вместе с уведомлением о выдаче
        else:
            sent = notify.status_changed(db, o)
    return {**order_dict(o), "notified": sent}


class LinkIn(BaseModel):
    server_link: str = Field(max_length=512)
    notify: bool = True

    @field_validator("server_link")
    @classmethod
    def https_only(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith("https://"):
            raise ValueError("Ссылка должна начинаться с https://")
        return v


@router.post("/orders/{oid}/server-link")
def set_link(oid: int, body: LinkIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    o.server_link = body.server_link or None
    audit(db, admin.username, "order_server_link", "order", o.id, {"set": bool(o.server_link)})
    db.commit()
    sent = False
    if body.notify and o.server_link:
        from bot import notify
        sent = notify.server_link(db, o)
    return {**order_dict(o), "notified": sent}


@router.post("/orders/{oid}/refund")
def refund_order(oid: int, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    if o.payment_status.value != "paid":
        raise HTTPException(400, "Заказ не оплачен — возвращать нечего")
    from bot.payments import refund
    if not refund(db, o, actor=admin.username):
        raise HTTPException(400, "Платёж не найден")
    audit(db, admin.username, "order_refund", "order", o.id, {"stars": o.total_stars})
    db.commit()
    from bot import notify
    notify.status_changed(db, o)
    return order_dict(o)


# ---------- Выдача и чеки (Этап 7) ----------
class DeliverIn(BaseModel):
    server_link: str = Field(min_length=1, max_length=512)
    comment: str | None = Field(None, max_length=500)

    @field_validator("server_link")
    @classmethod
    def https_only(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Ссылка должна начинаться с https://")
        return v


@router.post("/orders/{oid}/deliver")
def start_delivery(oid: int, body: DeliverIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    """Одно действие: сохранить ссылку, перевести в «Ожидает выдачи» и отправить ссылку покупателю."""
    o = _get_order(db, oid)
    old = o.status.value
    if old not in ("paid", "processing", "awaiting_delivery"):
        raise HTTPException(400, f"Выдача невозможна в статусе «{ORDER_STATUS_RU[old]}»")
    o.server_link = body.server_link
    if old != "awaiting_delivery":
        o.history.append(OrderStatusHistory(old_status=old, new_status="awaiting_delivery",
                                            changed_by=admin.username, comment=body.comment or "Отправлена ссылка на сервер"))
        o.status = OrderStatus.awaiting_delivery
    audit(db, admin.username, "order_deliver", "order", o.id, {"from": old})
    db.commit()
    from bot import notify
    return {**order_dict(o), "notified": notify.server_link(db, o)}


def _receipt_pdf(db: Session, o: Order) -> bytes:
    from app.receipt import build_receipt, can_have_receipt
    if not can_have_receipt(o):
        raise HTTPException(400, "Чек доступен только для оплаченного заказа")
    pay = db.scalar(select(Payment).where(Payment.order_id == o.id).order_by(Payment.id))
    shop = db.get(Setting, "shop_name")
    return build_receipt(o, pay, shop.value if shop and shop.value else "ChapaShop")


@router.get("/orders/{oid}/receipt.pdf")
def receipt_pdf(oid: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    return RawResponse(_receipt_pdf(db, o), media_type="application/pdf",
                       headers={"Content-Disposition": f'inline; filename="ChapaShop_chek_{o.number}.pdf"'})


@router.post("/orders/{oid}/send-receipt")
def send_receipt(oid: int, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    o = _get_order(db, oid)
    _receipt_pdf(db, o)  # проверка, что чек возможен
    from bot import notify
    sent = notify.receipt(db, o)
    audit(db, admin.username, "order_receipt_sent", "order", o.id, {"sent": sent})
    db.commit()
    return {"ok": True, "notified": sent}


# ---------- Товары ----------
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field("", max_length=2000)
    image_url: str | None = Field(None, max_length=512)
    category_id: int | None = None
    price_stars: int = Field(ge=1, le=100000)
    is_available: bool = True
    is_hidden: bool = False
    is_demo: bool = False

    @field_validator("image_url")
    @classmethod
    def safe_url(cls, v):
        if v in (None, ""):
            return None
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("/static/")):
            raise ValueError("Адрес картинки должен начинаться с https://")
        return v


def product_dict(p: Product) -> dict:
    return {"id": p.id, "name": p.name, "description": p.description, "image_url": p.image_url,
            "category_id": p.category_id, "price_stars": p.price_stars, "is_available": p.is_available,
            "is_hidden": p.is_hidden, "is_demo": p.is_demo}


@router.get("/products")
def admin_products(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    return {"products": [product_dict(p) for p in db.scalars(select(Product).order_by(Product.id.desc()))],
            "categories": [{"id": c.id, "name": c.name} for c in db.scalars(select(Category).order_by(Category.sort_order))]}


def _check_cat(db: Session, cid):
    if cid is not None and db.get(Category, cid) is None:
        raise HTTPException(400, "Категория не найдена")


@router.post("/products")
def create_product(body: ProductIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    _check_cat(db, body.category_id)
    p = Product(**body.model_dump())
    db.add(p)
    db.flush()
    audit(db, admin.username, "product_create", "product", p.id, {"name": p.name, "price": p.price_stars})
    db.commit()
    return product_dict(p)


@router.put("/products/{pid}")
def update_product(pid: int, body: ProductIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if p is None:
        raise HTTPException(404, "Товар не найден")
    _check_cat(db, body.category_id)
    changes = {k: [getattr(p, k), v] for k, v in body.model_dump().items() if getattr(p, k) != v}
    for k, (_, v) in changes.items():
        setattr(p, k, v)
    audit(db, admin.username, "product_update", "product", p.id, changes)
    db.commit()
    return product_dict(p)


@router.delete("/products/{pid}")
def delete_product(pid: int, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if p is None:
        raise HTTPException(404, "Товар не найден")
    # Старые заказы хранят снимок названия и цены, поэтому удаление их не ломает.
    audit(db, admin.username, "product_delete", "product", p.id, {"name": p.name})
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------- Покупатели ----------
@router.get("/customers")
def customers(_: Admin = Depends(current_admin), db: Session = Depends(get_db), q: str | None = None):
    paid = func.sum(Order.total_stars).filter(Order.payment_status == "paid")
    stmt = (select(User, func.count(Order.id), func.coalesce(paid, 0))
            .outerjoin(Order, Order.user_id == User.id).group_by(User.id).order_by(User.id.desc()))
    if q:
        q = q.strip()[:64]
        conds = [User.username.ilike(f"%{q}%"), User.roblox_username.ilike(f"%{q}%"), User.first_name.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(User.telegram_id == int(q))
        stmt = stmt.where(or_(*conds))
    return [{"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "first_name": u.first_name,
             "roblox_username": u.roblox_username, "orders": n, "spent_stars": s,
             "created_at": u.created_at.isoformat()} for u, n, s in db.execute(stmt.limit(200)).all()]


@router.get("/customers/{uid}")
def customer_detail(uid: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(404, "Покупатель не найден")
    return {"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "first_name": u.first_name,
            "roblox_username": u.roblox_username,
            "orders": [order_dict(o) for o in db.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.id.desc()))]}


# ---------- Настройки ----------
@router.get("/settings")
def get_settings_all(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    return {"settings": {s.key: s.value for s in db.scalars(select(Setting).order_by(Setting.key))},
            "secrets": get_settings().secrets_status()}


class SettingsIn(BaseModel):
    values: dict[str, str]


@router.put("/settings")
def put_settings(body: SettingsIn, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    changed = []
    for k, v in body.values.items():
        s = db.get(Setting, k)
        if s is None:
            raise HTTPException(400, f"Неизвестная настройка: {k}")
        if len(v) > 4000:
            raise HTTPException(400, f"Слишком длинное значение: {k}")
        if k == "maintenance_mode" and v not in ("0", "1"):
            raise HTTPException(400, "maintenance_mode: 0 или 1")
        if s.value != v:
            s.value = v
            changed.append(k)
    audit(db, admin.username, "settings_update", "settings", None, {"keys": changed})
    db.commit()
    return {"ok": True, "changed": changed}


# ---------- Журнал ----------
@router.get("/audit")
def audit_log(_: Admin = Depends(current_admin), db: Session = Depends(get_db), limit: int = 200):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)))
    return [{"id": a.id, "actor": a.actor, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "details": a.details, "at": a.created_at.isoformat()} for a in rows]


# ---------- Резервные копии и целостность (Этап 8) ----------
import json as _json

from app import backup as _backup
from app import integrity as _integrity

MAX_RESTORE_BYTES = 50 * 1024 * 1024


@router.get("/integrity")
def integrity(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    return _integrity.check(db)


@router.get("/backup")
def download_backup(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    payload = _backup.make_backup(db)
    name = _backup.save_backup_file(payload)
    audit(db, admin.username, "backup_create", "backup", None, {"file": name, "counts": payload["counts"]})
    db.commit()
    body = _json.dumps(payload, ensure_ascii=False).encode()
    return RawResponse(body, media_type="application/json",
                       headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/restore")
async def restore_backup(request: Request, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if request.headers.get("X-Confirm-Restore") != "YES":
        raise HTTPException(400, "Нужно подтверждение восстановления")
    raw = await request.body()
    if len(raw) > MAX_RESTORE_BYTES:
        raise HTTPException(413, "Файл слишком большой")
    try:
        payload = _json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Файл не является JSON")
    try:
        _backup.validate(payload)
        # Страховка: перед заменой сохраняем текущее состояние.
        safety = _backup.save_backup_file(_backup.make_backup(db))
        counts = _backup.restore(db, payload)
    except _backup.BackupError as e:
        raise HTTPException(400, str(e))
    audit(db, admin.username, "backup_restore", "backup", None, {"counts": counts, "safety_copy": safety})
    db.commit()
    return {"ok": True, "counts": counts, "safety_copy": safety}


@router.get("/preflight")
def preflight(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    """Этап 9: проверка готовности к запуску (без значений секретов)."""
    from app.preflight import run_checks, summary
    return summary(run_checks(db))
