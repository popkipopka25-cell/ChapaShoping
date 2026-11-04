import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Order, Payment, User, Product


def test_health_hides_secret_values(client):
    r = client.get("/health").json()
    assert r["status"] == "ok"
    assert all(isinstance(v, bool) for v in r["secrets_configured"].values())


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "ChapaShop" in r.text


def test_categories_seeded(client):
    assert [c["slug"] for c in client.get("/api/categories").json()] == ["pets", "eggs", "potions", "other"]


def test_products_all_demo(client):
    items = client.get("/api/products").json()
    assert len(items) == 6 and all(p["is_demo"] for p in items)


def test_filter_and_search(client):
    assert {p["category_id"] for p in client.get("/api/products?category=potions").json()} and \
        len(client.get("/api/products?category=potions").json()) == 2
    assert len(client.get("/api/products?q=дракон").json()) == 1


def test_sort_price(client):
    prices = [p["price_stars"] for p in client.get("/api/products?sort=price_asc").json()]
    assert prices == sorted(prices)


def test_hidden_product_not_shown(client):
    with SessionLocal() as db:
        p = db.query(Product).first(); p.is_hidden = True; pid = p.id; db.commit()
    assert client.get(f"/api/products/{pid}").status_code == 404
    assert pid not in [x["id"] for x in client.get("/api/products").json()]


def test_sql_injection_is_harmless(client):
    r = client.get("/api/products", params={"q": "' OR 1=1 --"})
    assert r.status_code == 200 and r.json() == []


def test_order_numbers_unique_and_padded(client):
    with SessionLocal() as db:
        u = User(telegram_id=1); db.add(u); db.flush()
        o1 = Order(user_id=u.id, telegram_id=1, roblox_username="a", total_stars=10)
        o2 = Order(user_id=u.id, telegram_id=1, roblox_username="a", total_stars=10)
        db.add_all([o1, o2]); db.commit()
        assert o1.number != o2.number and len(o1.number) == 5


def test_payment_charge_id_cannot_repeat(client):
    with SessionLocal() as db:
        u = User(telegram_id=2); db.add(u); db.flush()
        o = Order(user_id=u.id, telegram_id=2, roblox_username="b", total_stars=10); db.add(o); db.flush()
        db.add(Payment(order_id=o.id, telegram_payment_charge_id="X1", amount_stars=10)); db.commit()
        db.add(Payment(order_id=o.id, telegram_payment_charge_id="X1", amount_stars=10))
        with pytest.raises(IntegrityError):
            db.commit()
