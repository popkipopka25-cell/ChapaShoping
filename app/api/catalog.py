from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category, Product
from app.schemas import CategoryOut, ProductOut, CartQuoteIn, CartQuoteOut, CartLineOut
from app.config import get_settings
from app.models import Setting

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.sort_order)).all()


@router.get("/products", response_model=list[ProductOut])
def products(
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=64),
    category: str | None = Query(None, max_length=64),
    available: bool | None = None,
    sort: Literal["new", "price_asc", "price_desc", "name"] = "new",
):
    stmt = select(Product).where(Product.is_hidden.is_(False))
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q.strip()}%"))
    if category:
        stmt = stmt.join(Category).where(Category.slug == category)
    if available is not None:
        stmt = stmt.where(Product.is_available.is_(available))
    order = {"new": Product.id.desc(), "price_asc": Product.price_stars.asc(),
             "price_desc": Product.price_stars.desc(), "name": Product.name.asc()}[sort]
    return db.scalars(stmt.order_by(order)).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or p.is_hidden:
        raise HTTPException(404, "Товар не найден")
    return p


PUBLIC_SETTINGS = ("shop_name", "shop_description", "primary_color", "maintenance_mode",
                   "contact_info", "order_rules", "bot_username")
MAX_QTY = 99
MAX_LINES = 50


@router.get("/shop")
def shop_info(db: Session = Depends(get_db)):
    """Публичные настройки магазина (без секретов)."""
    rows = db.scalars(select(Setting).where(Setting.key.in_(PUBLIC_SETTINGS))).all()
    data = {r.key: r.value for r in rows}
    data["payments_enabled"] = bool(get_settings().bot_token)
    return data


@router.post("/cart/quote", response_model=CartQuoteOut)
def cart_quote(body: CartQuoteIn, db: Session = Depends(get_db)):
    """Пересчёт корзины на сервере: цены берутся только из базы, не от клиента."""
    if len(body.items) > MAX_LINES:
        raise HTTPException(400, "Слишком много позиций")
    merged: dict[int, int] = {}
    for line in body.items:
        if line.quantity < 1:
            continue
        merged[line.product_id] = min(MAX_QTY, merged.get(line.product_id, 0) + line.quantity)
    out, removed, total, count = [], [], 0, 0
    products_by_id = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(merged))).all()} if merged else {}
    for pid, qty in merged.items():
        p = products_by_id.get(pid)
        if p is None or p.is_hidden:
            removed.append(pid)
            continue
        sub = p.price_stars * qty if p.is_available else 0
        out.append(CartLineOut(product_id=p.id, name=p.name, price_stars=p.price_stars,
                               old_price_stars=p.old_price_stars, quantity=qty, subtotal=sub, available=p.is_available))
        if p.is_available:
            total += sub
            count += qty
            
    discount_amount = 0
    promo_applied = False
    if body.promo_code:
        from app.models import PromoCode
        pcode = db.scalar(select(PromoCode).where(PromoCode.code == body.promo_code.strip().upper()))
        if pcode and (pcode.max_uses is None or pcode.uses_count < pcode.max_uses):
            promo_applied = True
            discount_amount = int(total * (pcode.discount_percent / 100))
            total -= discount_amount

    return CartQuoteOut(items=out, total_stars=total, discount_amount=discount_amount, 
                        promo_applied=promo_applied, count=count, removed=removed)
