import pytest

from app.config import get_settings
from bot.telegram import OUTBOX

SECRET = "test-webhook-secret"


@pytest.fixture()
def bot(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_secret", SECRET)
    OUTBOX.clear()

    def send(update):
        return client.post("/telegram/webhook", json=update,
                           headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
    return send


def msg(text, uid=111, name="Дима"):
    return {"update_id": 1, "message": {"message_id": 1, "text": text,
            "from": {"id": uid, "first_name": name}, "chat": {"id": uid, "type": "private"}}}


def test_webhook_rejects_without_secret(client, bot):
    assert client.post("/telegram/webhook", json=msg("/start")).status_code == 401
    assert client.post("/telegram/webhook", json=msg("/start"),
                       headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 401


def test_webhook_closed_when_secret_not_configured(client):
    assert client.post("/telegram/webhook", json=msg("/start"),
                       headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 401


def test_start_creates_user_and_greets_with_shop_button(bot):
    assert bot(msg("/start")).status_code == 200
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        assert db.query(User).filter_by(telegram_id=111).one().first_name == "Дима"
    sent = OUTBOX[-1]
    assert "ChapaShop" in sent["text"] and "Дима" in sent["text"]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["text"].startswith("🛍")


def test_name_is_html_escaped(bot):
    bot(msg("/start", name="<b>x</b>"))
    assert "&lt;b&gt;" in OUTBOX[-1]["text"]


@pytest.mark.parametrize("cmd", ["/shop", "/help", "/profile", "/orders"])
def test_commands_reply(bot, cmd):
    bot(msg(cmd))
    assert OUTBOX and OUTBOX[-1]["chat_id"] == 111


def test_roblox_username_validation_and_save(bot):
    bot(msg("/roblox x"))
    assert "Укажите ник" in OUTBOX[-1]["text"]
    bot(msg("/roblox Player_123"))
    bot(msg("/profile"))
    assert "Player_123" in OUTBOX[-1]["text"]


def test_orders_lists_user_orders(bot):
    bot(msg("/start"))
    from app.db import SessionLocal
    from app.models import Order, User
    with SessionLocal() as db:
        u = db.query(User).filter_by(telegram_id=111).one()
        db.add(Order(user_id=u.id, telegram_id=111, roblox_username="P1", total_stars=150))
        db.commit()
    bot(msg("/orders"))
    assert "00001" in OUTBOX[-1]["text"] and "150 ⭐" in OUTBOX[-1]["text"]


def test_callback_button(bot):
    bot({"update_id": 2, "callback_query": {"id": "c1", "data": "profile",
         "from": {"id": 222, "first_name": "A"}}})
    assert any(m["method"] == "answerCallbackQuery" for m in OUTBOX)
    assert "Профиль" in OUTBOX[-1]["text"]


def test_notifications(bot):
    bot(msg("/start"))
    from app.db import SessionLocal
    from app.models import Order, OrderStatus, User
    from bot import notify
    with SessionLocal() as db:
        u = db.query(User).filter_by(telegram_id=111).one()
        o = Order(user_id=u.id, telegram_id=111, roblox_username="P1", total_stars=90)
        db.add(o); db.commit()
        notify.order_created(db, o); assert "00001" in OUTBOX[-1]["text"]
        assert notify.server_link(db, o) is False  # без ссылки не отправляем
        o.server_link = "https://www.roblox.com/share?code=abc"; o.status = OrderStatus.awaiting_delivery
        notify.server_link(db, o)
        assert OUTBOX[-1]["reply_markup"]["inline_keyboard"][0][0]["url"] == o.server_link
        notify.rejected(db, o, "<нет>"); assert "&lt;нет&gt;" in OUTBOX[-1]["text"]


def test_owner_can_change_welcome_text(bot):
    from app.db import SessionLocal
    from app.models import Setting
    with SessionLocal() as db:
        db.get(Setting, "bot_welcome").value = "Йо, {name}!"; db.commit()
    bot(msg("/start"))
    assert OUTBOX[-1]["text"] == "Йо, Дима!"


def test_broken_template_falls_back(bot):
    from app.db import SessionLocal
    from app.models import Setting
    with SessionLocal() as db:
        db.get(Setting, "bot_welcome").value = "Привет {oops}"; db.commit()
    bot(msg("/start"))
    assert "ChapaShop" in OUTBOX[-1]["text"]
