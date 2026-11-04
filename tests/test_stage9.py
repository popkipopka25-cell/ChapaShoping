"""Этап 9: предстартовая проверка."""
from app import preflight as pf
from app.config import get_settings
from app.db import SessionLocal
from tests.test_stage6 import login, owner  # noqa: F401


def _prod(mp, **kw):
    s = get_settings()
    vals = dict(app_env="production", secret_key="x" * 40, admin_password="очень-длинный-пароль",
                bot_token="123:abc", webhook_secret="s" * 32, public_url="https://shop.onrender.com",
                database_url="postgresql://u:p@h/db")
    vals.update(kw)
    for k, v in vals.items():
        mp.setattr(s, k, v)


def test_fully_configured_is_ready(monkeypatch):
    _prod(monkeypatch)
    assert pf.summary(pf.run_checks())["ready"] is True


def test_default_secret_key_blocks_launch(monkeypatch):
    _prod(monkeypatch, secret_key="dev-insecure-key")
    assert "SECRET_KEY" in pf.summary(pf.run_checks())["blockers"]


def test_http_url_and_sqlite_block_launch(monkeypatch):
    _prod(monkeypatch, public_url="http://x", database_url="sqlite:///a.db")
    b = pf.summary(pf.run_checks())["blockers"]
    assert "PUBLIC_URL" in b and "DATABASE" in b


def test_short_admin_password_blocks(monkeypatch):
    _prod(monkeypatch, admin_password="123")
    assert "ADMIN_PASSWORD" in pf.summary(pf.run_checks())["blockers"]


def test_development_never_blocks(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "development")
    assert pf.summary(pf.run_checks())["ready"] is True


def test_db_check_counts_products(client):
    with SessionLocal() as db:
        keys = {c["key"]: c for c in pf.run_checks(db)}
    assert keys["DB_CONNECT"]["ok"]


def test_preflight_endpoint_needs_login_and_hides_secrets(owner):
    assert owner.get("/admin/api/preflight").status_code == 401
    login(owner)
    r = owner.get("/admin/api/preflight")
    assert r.status_code == 200 and "ready" in r.json()
    assert get_settings().admin_password not in r.text


def test_admin_panel_has_readiness_tab(client):
    html = client.get("/admin").text
    js = client.get("/static/admin.js").text
    assert 'data-tab="ready"' in html and '"/preflight"' in js
