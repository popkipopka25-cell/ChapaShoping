"""Демо-данные. Только вымышленные товары с пометкой «Демо»."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Product, Setting
from bot.texts import DEFAULTS as BOT_TEXTS

# Используем unicode-escape для гарантии правильной кодировки
def u(s):
    return s.encode('ascii').decode('unicode-escape')

CATEGORIES = [
    ("pets", u("\u041f\u0438\u0442\u043e\u043c\u0446\u044b"), 1),
    ("eggs", u("\u042f\u0439\u0446\u0430"), 2),
    ("potions", u("\u0417\u0435\u043b\u044c\u044f"), 3),
    ("other", u("\u0414\u0440\u0443\u0433\u043e\u0435"), 4)
]

PRODUCTS = [
    (u("\u0414\u0435\u043c\u043e-\u043f\u0438\u0442\u043e\u043c\u0435\u0446 \u00ab\u041b\u0443\u043d\u043d\u044b\u0439 \u043b\u0438\u0441\u00bb"), "pets", 250, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
    (u("\u0414\u0435\u043c\u043e-\u043f\u0438\u0442\u043e\u043c\u0435\u0446 \u00ab\u0421\u0430\u043f\u0444\u0438\u0440\u043e\u0432\u044b\u0439 \u0434\u0440\u0430\u043a\u043e\u043d\u00bb"), "pets", 480, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
    (u("\u0414\u0435\u043c\u043e-\u044f\u0439\u0446\u043e \u00ab\u0417\u0432\u0451\u0437\u0434\u043d\u043e\u0435\u00bb"), "eggs", 90, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
    (u("\u0414\u0435\u043c\u043e-\u0437\u0435\u043b\u044c\u0435 \u00ab\u041f\u043e\u043b\u0451\u0442\u00bb"), "potions", 60, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
    (u("\u0414\u0435\u043c\u043e-\u0437\u0435\u043b\u044c\u0435 \u00ab\u041d\u0435\u043e\u043d\u00bb"), "potions", 75, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
    (u("\u0414\u0435\u043c\u043e-\u043d\u0430\u0431\u043e\u0440 \u00ab\u041d\u043e\u0432\u0438\u0447\u043e\u043a\u00bb"), "other", 150, u("\u0422\u0435\u0441\u0442\u043e\u0432\u044b\u0439 \u0442\u043e\u0432\u0430\u0440.")),
]

SETTINGS = {
    "shop_name": "ChapaShop",
    "shop_description": u("\u041c\u0430\u0433\u0430\u0437\u0438\u043d \u0442\u043e\u0432\u0430\u0440\u043e\u0432 Adopt Me"),
    "primary_color": "#7B2FF7",
    "maintenance_mode": "0",
    "contact_info": u("\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430: @ChapikSupport"),
    "order_rules": u("\u041f\u043e\u0441\u043b\u0435 \u043e\u043f\u043b\u0430\u0442\u044b \u0443\u043a\u0430\u0436\u0438\u0442\u0435 \u0432\u0435\u0440\u043d\u044b\u0439 Roblox username."),
    "bot_username": "",
}

def seed(db: Session) -> None:
    try:
        # Очищаем всё, что было
        db.query(Product).delete()
        db.query(Category).delete()
        db.commit()

        # Создаем категории и товары
        cats = {}
        for slug, name, order in CATEGORIES:
            c = Category(slug=slug, name=name, sort_order=order)
            db.add(c)
            db.flush()
            cats[slug] = c
        
        for name, slug, price, desc in PRODUCTS:
            db.add(Product(name=name, category_id=cats[slug].id, price_stars=price,
                           description=desc, is_demo=True))
        
        # Добавляем настройки, если их нет
        for k, v in {**SETTINGS, **BOT_TEXTS}.items():
            if db.get(Setting, k) is None:
                db.add(Setting(key=k, value=v))
        
        db.commit()
    except Exception as e:
        print("Ошибка при заполнении базы:", e)
        db.rollback()
