"""Этап 5: оплата Telegram Stars."""
import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.models import Order, Payment
from bot.telegram import OUTBOX
from tests.test_stage3 import SECRET
from tests.test_stage4 import tg  # noqa: F401  (фикстура)


@pytest.fixture()
def hook(client, tg, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_secret", SECRET)
    OUTBOX.clear()
    import bot.handlers as bh, bot.payments as bp, bot.telegram as bt
    rec = lambda m, **p: OUTBOX.append({"method": m, **p})
    for mod in (bh, bp, bt):
        monkeypatch.setattr(mod, "call", rec)
    return lambda u: client.post("/telegram/webhook", json=u, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})


def make_order(client, tg, uid=777):
    p = client.get("/api/products?available=true").json()[0]
    return client.post("/api/orders", headers=tg(uid=uid), json={"roblox_username": "Player_1",
                       "items": [{"product_id": p["id"], "quantity": 2}]}).json()


def precheckout(o, uid=777, amount=None):
    return {"update_id": 10, "pre_checkout_query": {"id": "pq1", "from": {"id": uid}, "currency": "XTR",
            "total_amount": o["total_stars"] if amount is None else amount, "invoice_payload": f"order:{o['id']}"}}


def paid(o, charge="ch_1", uid=777, amount=None):
    return {"update_id": 11, "message": {"message_id": 5, "from": {"id": uid}, "chat": {"id": uid, "type": "private"},
            "successful_payment": {"currency": "XTR", "total_amount": o["total_stars"] if amount is None else amount,
                                   "invoice_payload": f"order:{o['id']}", "telegram_payment_charge_id": charge,
                                   "provider_payment_charge_id": ""}}}


def calls(method):
    return [c for c in OUTBOX if c["method"] == method]


def test_order_notification_has_pay_button(client, tg, hook, monkeypatch):
    calls_ = []
    import bot.telegram as bt
    monkeypatch.setattr(bt, "call", lambda m, **p: calls_.append({"method": m, **p}))
    o = make_order(client, tg)
    msg = [c for c in calls_ if c["method"] == "sendMessage"][-1]
    assert msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"pay:{o['id']}"


def test_invoice_params(client, tg, monkeypatch):
    seen = {}
    import bot.payments as bp
    monkeypatch.setattr(bp, "call", lambda m, **p: seen.update(method=m, **p) or "https://t.me/$abc")
    o = make_order(client, tg)
    r = client.post(f"/api/orders/{o['id']}/invoice", headers=tg())
    assert r.json()["invoice_link"] == "https://t.me/$abc"
    assert seen["method"] == "createInvoiceLink" and seen["currency"] == "XTR" and seen["provider_token"] == ""
    assert seen["prices"][0]["amount"] == o["total_stars"] and seen["payload"] == f"order:{o['id']}"
    assert client.post(f"/api/orders/{o['id']}/invoice", headers=tg(uid=5)).status_code == 404


def test_invoice_test_mode_not_faked(client, tg, monkeypatch):
    import bot.payments as bp
    monkeypatch.setattr(bp, "call", lambda m, **p: None)
    o = make_order(client, tg)
    assert client.post(f"/api/orders/{o['id']}/invoice", headers=tg()).status_code == 503
    assert client.get(f"/api/orders/{o['id']}", headers=tg()).json()["payment_status"] == "pending"


def test_precheckout_ok_and_rejects(client, tg, hook):
    o = make_order(client, tg)
    OUTBOX.clear()
    hook(precheckout(o))
    assert calls("answerPreCheckoutQuery")[-1]["ok"] is True
    hook(precheckout(o, amount=1))
    a = calls("answerPreCheckoutQuery")[-1]
    assert a["ok"] is False and a["error_message"]
    hook(precheckout(o, uid=999))
    assert calls("answerPreCheckoutQuery")[-1]["ok"] is False
    # pre_checkout сам по себе не делает заказ оплаченным
    assert client.get(f"/api/orders/{o['id']}", headers=tg()).json()["payment_status"] == "pending"


def test_successful_payment_marks_paid_once(client, tg, hook):
    o = make_order(client, tg)
    hook(paid(o))
    got = client.get(f"/api/orders/{o['id']}", headers=tg()).json()
    assert got["payment_status"] == "paid" and got["status"] == "paid"
    assert [h["status"] for h in got["history"]] == ["awaiting_payment", "paid"]
    hook(paid(o))  # повтор того же платежа
    hook(precheckout(o))
    assert calls("answerPreCheckoutQuery")[-1]["ok"] is False  # повторная оплата закрыта
    with SessionLocal() as db:
        assert db.query(Payment).count() == 1
        assert db.get(Order, o["id"]).history[-1].new_status == "paid"
        assert len(db.get(Order, o["id"]).history) == 2


def test_wrong_amount_payment_goes_to_review(client, tg, hook):
    o = make_order(client, tg)
    hook(paid(o, charge="ch_bad", amount=1))
    assert client.get(f"/api/orders/{o['id']}", headers=tg()).json()["payment_status"] == "pending"
    with SessionLocal() as db:
        assert db.query(Payment).one().status == "needs_review"


def test_pay_callback_sends_invoice(client, tg, hook):
    o = make_order(client, tg)
    OUTBOX.clear()
    hook({"update_id": 3, "callback_query": {"id": "c", "data": f"pay:{o['id']}", "from": {"id": 777, "first_name": "A"}}})
    inv = calls("sendInvoice")
    assert inv and inv[0]["currency"] == "XTR" and inv[0]["chat_id"] == 777
    OUTBOX.clear()
    hook({"update_id": 4, "callback_query": {"id": "c", "data": f"pay:{o['id']}", "from": {"id": 5, "first_name": "B"}}})
    assert not calls("sendInvoice")
