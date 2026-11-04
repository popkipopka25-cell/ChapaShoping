@router.post("/cart/quote", response_model=CartQuoteOut)
def cart_quote(body: CartQuoteIn, db: Session = Depends(get_db)):
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
            
    # Логика промокода
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
