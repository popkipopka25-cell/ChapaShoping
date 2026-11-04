def _ids(client):
    return {p["name"]: p for p in client.get("/api/products").json()}


def test_pages_served(client):
    for path in ("/", "/cart", "/about", "/product/1"):
        r = client.get(path)
        assert r.status_code == 200 and "ChapaShop" in r.text


def test_shop_info_has_no_secrets(client):
    data = client.get("/api/shop").json()
    assert data["shop_name"] == "ChapaShop"
    assert data["payments_enabled"] is False
    assert "bot_token" not in data and "admin_password" not in data


def test_cart_quote_uses_server_prices(client):
    p = next(iter(_ids(client).values()))
    r = client.post("/api/cart/quote", json={"items": [
        {"product_id": p["id"], "quantity": 2}, {"product_id": p["id"], "quantity": 1}]})
    body = r.json()
    assert body["total_stars"] == p["price_stars"] * 3
    assert body["count"] == 3 and body["items"][0]["quantity"] == 3


def test_cart_quote_caps_quantity_and_drops_unknown(client):
    p = next(iter(_ids(client).values()))
    body = client.post("/api/cart/quote", json={"items": [
        {"product_id": p["id"], "quantity": 500}, {"product_id": 99999, "quantity": 1},
        {"product_id": p["id"] + 0, "quantity": 0}]}).json()
    assert body["items"][0]["quantity"] == 99
    assert body["removed"] == [99999]


def test_cart_quote_excludes_hidden_and_unavailable(client):
    from app.db import SessionLocal
    from app.models import Product
    prods = list(_ids(client).values())
    with SessionLocal() as db:
        db.get(Product, prods[0]["id"]).is_hidden = True
        db.get(Product, prods[1]["id"]).is_available = False
        db.commit()
    body = client.post("/api/cart/quote", json={"items": [
        {"product_id": prods[0]["id"], "quantity": 1}, {"product_id": prods[1]["id"], "quantity": 2}]}).json()
    assert body["removed"] == [prods[0]["id"]]
    assert body["total_stars"] == 0 and body["items"][0]["available"] is False


def test_available_filter(client):
    from app.db import SessionLocal
    from app.models import Product
    pid = next(iter(_ids(client).values()))["id"]
    with SessionLocal() as db:
        db.get(Product, pid).is_available = False
        db.commit()
    ids = [p["id"] for p in client.get("/api/products?available=true").json()]
    assert pid not in ids
