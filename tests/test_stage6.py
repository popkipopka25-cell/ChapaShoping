"""Этап 6: панель владельца."""
import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.models import Admin, AuditLog, Order, Product
from app.security import hash_password, verify_password
from app.api import admin as admin_api
from bot.telegram import OUTBOX
from tests.test_stage4 import tg  # noqa: F401
from tests.test_stage5 import hook, make_order, paid  # noqa: F401

PW = "owner-pass-123"


@pytest.fixture()
def owner(client, monkeypatch):
    admin_api._fails.clear()
    monkeypatch.setattr(get_settings(), "admin_password", PW)
    with SessionLocal() as db:
        admin_api.ensure_owner(db)
    return client


def login(c, pw=PW):
    r = c.post("/admin/api/login", json={"username": "owner", "password": pw})
    return r, (r.json().get("csrf") if r.status_code == 200 else None)


def test_password_hashing():
    h = hash_password("секрет")
    assert h != "секрет" and verify_password("секрет", h) and not verify_password("другой", h)


def test_owner_created_with_hash(owner):
    with SessionLocal() as db:
        a = db.query(Admin).one()
        assert a.username == "owner" and PW not in a.password_hash


def test_panel_requires_login(owner):
    for path in ("/admin/api/orders", "/admin/api/products", "/admin/api/customers",
                 "/admin/api/settings", "/admin/api/audit", "/admin/api/stats"):
        assert owner.get(path).status_code == 401
    assert owner.get("/admin").status_code == 200  # страница входа открыта


def test_wrong_password_and_rate_limit(owner):
    for _ in range(5):
        assert login(owner, "bad")[0].status_code == 401
    assert login(owner)[0].status_code == 429


def test_login_and_csrf(owner):
    r, csrf = login(owner)
    assert r.status_code == 200 and csrf
    assert owner.get("/admin/api/me").status_code == 200
    body = {"values": {"shop_name": "X"}}
    assert owner.put("/admin/api/settings", json=body).status_code == 403
    assert owner.put("/admin/api/settings", json=body, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert owner.get("/api/shop").json()["shop_name"] == "X"


def test_forged_cookie_rejected(owner):
    owner.cookies.set("cs_admin", "1.9999999999.deadbeef", path="/admin")
    assert owner.get("/admin/api/me").status_code == 401


def test_product_crud_and_price(owner):
    _, csrf = login(owner)
    h = {"X-CSRF-Token": csrf}
    cats = owner.get("/admin/api/products").json()["categories"]
    p = owner.post("/admin/api/products", headers=h, json={"name": "Тест", "price_stars": 10, "category_id": cats[0]["id"]}).json()
    assert any(x["id"] == p["id"] for x in owner.get("/api/products").json())
    upd = {**p, "price_stars": 33, "is_hidden": True}
    upd.pop("id")
    assert owner.put(f"/admin/api/products/{p['id']}", headers=h, json=upd).json()["price_stars"] == 33
    assert owner.get(f"/api/products/{p['id']}").status_code == 404  # скрыт
    bad = {**upd, "image_url": "javascript:alert(1)"}
    assert owner.put(f"/admin/api/products/{p['id']}", headers=h, json=bad).status_code == 422
    assert owner.post("/admin/api/products", headers=h, json={"name": "x", "price_stars": 0}).status_code == 422
    assert owner.delete(f"/admin/api/products/{p['id']}", headers=h).status_code == 200
    with SessionLocal() as db:
        assert db.get(Product, p["id"]) is None
        acts = [a.action for a in db.query(AuditLog)]
    assert {"product_create", "product_update", "product_delete"} <= set(acts)


def test_order_flow_status_link_notifications(owner, tg, hook):
    o = make_order(owner, tg)
    _, csrf = login(owner)
    h = {"X-CSRF-Token": csrf}
    # до оплаты нельзя «Выдан»
    assert owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "delivered"}).status_code == 400
    hook(paid(o))
    OUTBOX.clear()
    r = owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "processing"})
    assert r.status_code == 200 and r.json()["status"] == "processing"
    assert owner.post(f"/admin/api/orders/{o['id']}/server-link", headers=h, json={"server_link": "http://x"}).status_code == 422
    assert owner.post(f"/admin/api/orders/{o['id']}/server-link", headers=h,
                      json={"server_link": "https://www.roblox.com/share?code=1"}).status_code == 200
    r = owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "delivered"})
    assert r.json()["status"] == "delivered"
    msgs = [c for c in OUTBOX if c["method"] == "sendMessage"]
    assert len(msgs) == 3 and all(m["chat_id"] == 777 for m in msgs)
    d = owner.get(f"/admin/api/orders/{o['id']}").json()
    assert [x["new"] for x in d["history"]] == ["awaiting_payment", "paid", "processing", "delivered"]
    assert d["payments"][0]["charge_id"] == "ch_1"
    assert owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "processing"}).status_code == 400


def test_reject_with_reason_and_refund(owner, tg, hook):
    o = make_order(owner, tg)
    _, csrf = login(owner)
    h = {"X-CSRF-Token": csrf}
    OUTBOX.clear()
    owner.post(f"/admin/api/orders/{o['id']}/status", headers=h, json={"status": "rejected", "comment": "<b>нет</b>"})
    txt = [c for c in OUTBOX if c["method"] == "sendMessage"][-1]["text"]
    assert "&lt;b&gt;нет" in txt
    o2 = make_order(owner, tg)
    hook(paid(o2, charge="ch_2"))
    r = owner.post(f"/admin/api/orders/{o2['id']}/refund", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "refunded"
    assert any(c["method"] == "refundStarPayment" for c in OUTBOX)
    assert owner.post(f"/admin/api/orders/{o2['id']}/refund", headers=h).status_code == 400


def test_customers_orders_search_stats(owner, tg, hook):
    o = make_order(owner, tg)
    hook(paid(o))
    login(owner)
    cs = owner.get("/admin/api/customers").json()
    assert cs[0]["telegram_id"] == 777 and cs[0]["spent_stars"] == o["total_stars"]
    assert owner.get(f"/admin/api/customers/{cs[0]['id']}").json()["orders"][0]["id"] == o["id"]
    assert len(owner.get("/admin/api/orders?q=Player_1").json()) == 1
    assert len(owner.get("/admin/api/orders?status=paid").json()) == 1
    assert owner.get("/admin/api/orders?status=hack").status_code == 400
    assert owner.get("/admin/api/stats").json()["revenue_stars"] == o["total_stars"]


def test_password_change_invalidates_old_session(owner):
    _, csrf = login(owner)
    old = owner.cookies.get("cs_admin")
    r = owner.post("/admin/api/password", headers={"X-CSRF-Token": csrf},
                   json={"old_password": PW, "new_password": "new-pass-456"})
    assert r.status_code == 200
    owner.cookies.set("cs_admin", old, path="/admin")
    assert owner.get("/admin/api/me").status_code == 401
    assert login(owner, "new-pass-456")[0].status_code == 200


def test_unknown_setting_rejected(owner):
    _, csrf = login(owner)
    assert owner.put("/admin/api/settings", headers={"X-CSRF-Token": csrf},
                     json={"values": {"bot_token": "x"}}).status_code == 400
