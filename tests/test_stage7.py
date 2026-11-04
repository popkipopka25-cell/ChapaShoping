"""Этап 7: выдача заказов и PDF-чеки."""
from app.db import SessionLocal
from app.models import Order, Payment
from app.receipt import build_receipt
from bot.telegram import OUTBOX
from tests.test_stage4 import tg  # noqa: F401
from tests.test_stage5 import hook, make_order, paid  # noqa: F401
from tests.test_stage6 import login, owner  # noqa: F401

LINK = "https://www.roblox.com/share?code=abc"


def docs():
    return [c for c in OUTBOX if c["method"] == "sendDocument"]


def test_receipt_pdf_has_cyrillic_and_amount(owner, tg, hook):
    o = make_order(owner, tg)
    hook(paid(o))
    with SessionLocal() as db:
        order = db.get(Order, o["id"])
        pdf = build_receipt(order, db.query(Payment).first())
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000


def test_no_receipt_before_payment(owner, tg, hook):
    o = make_order(owner, tg)
    _, csrf = login(owner)
    assert owner.get(f"/admin/api/orders/{o['id']}/receipt.pdf").status_code == 400
    assert owner.post(f"/admin/api/orders/{o['id']}/send-receipt", headers={"X-CSRF-Token": csrf}).status_code == 400
    assert owner.post(f"/api/orders/{o['id']}/receipt", headers=tg()).status_code == 400


def test_full_delivery_flow(owner, tg, hook):
    o = make_order(owner, tg)
    _, csrf = login(owner)
    h = {"X-CSRF-Token": csrf}
    assert owner.post(f"/admin/api/orders/{o['id']}/deliver", headers=h, json={"server_link": LINK}).status_code == 400
    hook(paid(o))
    OUTBOX.clear()
    assert owner.post(f"/admin/api/orders/{o['id']}/deliver", headers=h, json={"server_link": "http://bad"}).status_code == 422
    r = owner.post(f"/admin/api/orders/{o['id']}/deliver", headers=h, json={"server_link": LINK})
    assert r.status_code == 200 and r.json()["status"] == "awaiting_delivery"
    msg = [c for c in OUTBOX if c["method"] == "sendMessage"][-1]
    assert LINK in str(msg["reply_markup"])
    # покупатель видит ссылку
    assert owner.get(f"/api/orders/{o['id']}", headers=tg()).json()["server_link"] == LINK
    owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "delivered"})
    d = docs()
    assert len(d) == 1 and d[0]["chat_id"] == 777 and d[0]["filename"].endswith(".pdf")
    hist = [x["new"] for x in owner.get(f"/admin/api/orders/{o['id']}").json()["history"]]
    assert hist == ["awaiting_payment", "paid", "awaiting_delivery", "delivered"]
    pdf = owner.get(f"/admin/api/orders/{o['id']}/receipt.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"


def test_customer_receipt_request_and_ownership(owner, tg, hook):
    o = make_order(owner, tg)
    hook(paid(o))
    OUTBOX.clear()
    assert owner.get(f"/api/orders/{o['id']}", headers=tg()).json()["has_receipt"] is True
    assert owner.post(f"/api/orders/{o['id']}/receipt", headers=tg(uid=999)).status_code == 404
    for _ in range(3):
        assert owner.post(f"/api/orders/{o['id']}/receipt", headers=tg()).status_code == 200
    assert owner.post(f"/api/orders/{o['id']}/receipt", headers=tg()).status_code == 429
    assert len(docs()) == 3


def test_rejection_reason_visible_to_customer(owner, tg, hook):
    o = make_order(owner, tg)
    _, csrf = login(owner)
    owner.post(f"/admin/api/orders/{o['id']}/status", headers={"X-CSRF-Token": csrf},
               json={"status": "rejected", "comment": "Неверный ник"})
    h = owner.get(f"/api/orders/{o['id']}", headers=tg()).json()["history"]
    assert h[-1]["status"] == "rejected" and h[-1]["comment"] == "Неверный ник"


def test_refunded_receipt_marked(owner, tg, hook):
    o = make_order(owner, tg)
    hook(paid(o))
    _, csrf = login(owner)
    owner.post(f"/admin/api/orders/{o['id']}/refund", headers={"X-CSRF-Token": csrf})
    assert owner.get(f"/admin/api/orders/{o['id']}/receipt.pdf").status_code == 200
