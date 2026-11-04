"""Этап 8: безопасность, резервные копии, целостность, миграции, обработка ошибок."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import backup as bk
from app.db import SessionLocal
from app.models import Order, Payment, Product
from main import app
from tests.test_stage4 import tg  # noqa: F401
from tests.test_stage5 import hook, make_order, paid  # noqa: F401
from tests.test_stage6 import login, owner  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _tmp_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "BACKUP_DIR", tmp_path)


def H(csrf, **extra):
    return {"X-CSRF-Token": csrf, **extra}


def test_every_admin_route_requires_login(owner):
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/admin/api") or path.endswith("/login"):
            continue
        url = path.replace("{oid}", "1").replace("{pid}", "1").replace("{uid}", "1")
        for m in r.methods - {"HEAD", "OPTIONS"}:
            assert owner.request(m, url).status_code == 401, (m, url)


def test_backup_excludes_admin_and_has_checksum(owner):
    _, csrf = login(owner)
    r = owner.get("/admin/api/backup")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert "admins" not in d["data"] and "password_hash" not in r.text
    assert d["counts"]["products"] > 0 and len(d["checksum"]) == 64
    assert list(bk.BACKUP_DIR.glob("chapashop_*.json"))


def test_restore_roundtrip(owner, tg, hook):
    _, csrf = login(owner)
    o = make_order(owner, tg)
    hook(paid(o, charge="ch_bk"))
    snap = owner.get("/admin/api/backup").content
    with SessionLocal() as db:
        db.query(Payment).delete(); db.query(Product).update({Product.price_stars: 1}); db.commit()
    r = owner.post("/admin/api/restore", content=snap, headers=H(csrf, **{"X-Confirm-Restore": "YES"}))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.query(Payment).filter_by(telegram_payment_charge_id="ch_bk").count() == 1
        assert db.get(Order, o["id"]).status.value == "paid"
        assert db.query(Product).filter(Product.price_stars == 1).count() == 0
    # Вход владельца после восстановления продолжает работать
    assert login(owner)[0].status_code == 200
    # Новые записи после восстановления создаются без конфликта id
    assert make_order(owner, tg)["id"]


def test_restore_rejects_tampered_file(owner):
    _, csrf = login(owner)
    d = owner.get("/admin/api/backup").json()
    d["data"]["products"][0]["price_stars"] = 0
    r = owner.post("/admin/api/restore", content=json.dumps(d), headers=H(csrf, **{"X-Confirm-Restore": "YES"}))
    assert r.status_code == 400 and "Контрольная сумма" in r.json()["detail"]


def test_restore_needs_confirm_and_csrf(owner):
    _, csrf = login(owner)
    snap = owner.get("/admin/api/backup").content
    assert owner.post("/admin/api/restore", content=snap, headers=H(csrf)).status_code == 400
    assert owner.post("/admin/api/restore", content=snap, headers={"X-Confirm-Restore": "YES"}).status_code == 403
    assert owner.post("/admin/api/restore", content=b"not json",
                      headers=H(csrf, **{"X-Confirm-Restore": "YES"})).status_code == 400


def test_integrity_detects_problems(owner, tg, hook):
    login(owner)
    o = make_order(owner, tg)
    assert owner.get("/admin/api/integrity").json()["ok"] is True
    with SessionLocal() as db:
        db.get(Order, o["id"]).total_stars = 1; db.commit()
    ch = owner.get("/admin/api/integrity").json()
    assert ch["ok"] is False and any(p["order"] == o["id"] for p in ch["problems"])


def test_duplicate_payment_is_ignored(client, tg, hook):
    o = make_order(client, tg)
    hook(paid(o, charge="dup")); hook(paid(o, charge="dup"))
    with SessionLocal() as db:
        assert db.query(Payment).filter_by(telegram_payment_charge_id="dup").count() == 1


def test_errors_do_not_leak(client):
    from fastapi import APIRouter
    rt = APIRouter()

    @rt.get("/__boom")
    def boom():
        raise RuntimeError("secret-token-123")
    app.include_router(rt)
    r = client.get("/__boom")
    assert r.status_code == 500 and "secret-token-123" not in r.text


def test_body_size_limit_and_headers(client):
    r = client.post("/api/cart/quote", content=b"x" * (1024 * 1024 + 10), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    h = client.get("/").headers
    assert "frame-ancestors" in h["content-security-policy"] and h["x-content-type-options"] == "nosniff"


def test_migrations_match_models(tmp_path):
    db = tmp_path / "mig.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr
    code = ("from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata;"
            "from sqlalchemy import create_engine; from app.db import Base; import app.models;"
            f"e=create_engine('sqlite:///{db}');"
            "d=[x for x in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata)];print(len(d)); print(d)")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.stdout.splitlines()[0] == "0", r.stdout + r.stderr
