"""Этап 4: Telegram Mini App — авторизация initData, профиль, заказы."""
import json
import time

import pytest

from app.config import get_settings
from app.tg_auth import InitDataError, sign_init_data, verify_init_data

TOKEN = "123456:TEST-token"


@pytest.fixture()
def tg(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "bot_token", TOKEN)
    import bot.telegram as bt
    monkeypatch.setattr(bt, "call", lambda *a, **k: {"ok": True}, raising=False)

    def headers(uid=777, name="Ann", auth_date=None):
        data = sign_init_data({"auth_date": str(auth_date or int(time.time())), "query_id": "q",
                               "user": json.dumps({"id": uid, "first_name": name, "username": "ann"})}, TOKEN)
        return {"X-Telegram-Init-Data": data}
    return headers


def test_verify_ok_and_tampered():
    s = sign_init_data({"auth_date": str(int(time.time())), "user": json.dumps({"id": 5})}, TOKEN)
    assert verify_init_data(s, TOKEN)["id"] == 5
    with pytest.raises(InitDataError):
        verify_init_data(s.replace("%22id%22%3A+5", "%22id%22%3A+6"), TOKEN)
    with pytest.raises(InitDataError):
        verify_init_data(s, "999:other")


def test_verify_expired():
    s = sign_init_data({"auth_date": str(int(time.time()) - 200000), "user": json.dumps({"id": 5})}, TOKEN)
    with pytest.raises(InitDataError):
        verify_init_data(s, TOKEN)


def test_api_requires_init_data(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/me", headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=abc"}).status_code == 401


def test_profile_and_roblox(client, tg):
    r = client.get("/api/me", headers=tg())
    assert r.status_code == 200 and r.json()["telegram_id"] == 777
    assert client.put("/api/me/roblox", json={"roblox_username": "bad nick!"}, headers=tg()).status_code == 422
    assert client.put("/api/me/roblox", json={"roblox_username": "Player_1"}, headers=tg()).status_code == 200
    assert client.get("/api/me", headers=tg()).json()["roblox_username"] == "Player_1"


def test_create_order_server_prices_and_history(client, tg):
    p = client.get("/api/products?available=true").json()[0]
    r = client.post("/api/orders", headers=tg(), json={"roblox_username": "Player_1",
                    "items": [{"product_id": p["id"], "quantity": 2}]})
    assert r.status_code == 201
    o = r.json()
    assert o["total_stars"] == p["price_stars"] * 2
    assert o["status"] == "awaiting_payment" and o["payment_status"] == "pending"
    assert len(o["number"]) == 5 and not o["number"].startswith("#")
    lst = client.get("/api/orders", headers=tg()).json()
    assert [x["id"] for x in lst] == [o["id"]]
    assert client.get(f"/api/orders/{o['id']}", headers=tg()).json()["history"][0]["status"] == "awaiting_payment"


def test_foreign_order_hidden(client, tg):
    p = client.get("/api/products?available=true").json()[0]
    o = client.post("/api/orders", headers=tg(uid=1), json={"roblox_username": "Aaa", "items": [{"product_id": p["id"], "quantity": 1}]}).json()
    assert client.get(f"/api/orders/{o['id']}", headers=tg(uid=2)).status_code == 404
    assert client.get("/api/orders", headers=tg(uid=2)).json() == []


def test_order_rejects_unavailable_and_unique_numbers(client, tg):
    assert client.post("/api/orders", headers=tg(), json={"roblox_username": "Aaa", "items": [{"product_id": 99999, "quantity": 1}]}).status_code == 409
    p = client.get("/api/products?available=true").json()[0]
    nums = {client.post("/api/orders", headers=tg(uid=50 + i), json={"roblox_username": "Aaa", "items": [{"product_id": p["id"], "quantity": 1}]}).json()["number"] for i in range(4)}
    assert len(nums) == 4


def test_miniapp_pages_served(client):
    for path in ("/app", "/orders", "/orders/1", "/profile"):
        assert client.get(path).status_code == 200
