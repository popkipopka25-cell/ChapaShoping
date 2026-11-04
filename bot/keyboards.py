from app.config import get_settings

def miniapp_url() -> str:
    # ВАЖНО: здесь должен быть /app, а не /admin
    return get_settings().public_url.rstrip("/") + "/app"

def site_url() -> str:
    return get_settings().public_url.rstrip("/") + "/"

def _shop_button(label: str = "🛍 Открыть ChapaShop") -> dict:
    url = miniapp_url()
    if url.startswith("https://"):
        return {"text": label, "web_app": {"url": url}}
    return {"text": label, "url": site_url()}

def main_menu(open_label: str | None = None) -> dict:
    return {"inline_keyboard": [
        [_shop_button(open_label or "🛍 Открыть ChapaShop")],
        [{"text": "📦 Мои заказы", "callback_data": "orders"}, {"text": "👤 Профиль", "callback_data": "profile"}],
        [{"text": "💬 Поддержка", "url": "https://t.me/ChapikSupport"}],
        [{"text": "❓ Помощь", "callback_data": "help"}],
    ]}

def shop_only() -> dict:
    return {"inline_keyboard": [[_shop_button()]]}

def order_buttons(server_link: str | None = None) -> dict:
    rows = []
    if server_link:
        rows.append([{"text": "🎮 Зайти на сервер", "url": server_link}])
    rows.append([{"text": "📦 Мои заказы", "callback_data": "orders"}])
    rows.append([{"text": "💬 Поддержка", "url": "https://t.me/ChapikSupport"}])
    return {"inline_keyboard": rows}
