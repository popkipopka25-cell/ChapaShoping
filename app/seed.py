"""Демо-данные. Только вымышленные товары с пометкой «Демо»."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Product, Setting
from bot.texts import DEFAULTS as BOT_TEXTS


def fix_encoding(text):
    """Переводит кракозябры (latin-1) обратно в русский (utf-8)."""
    if not text:
        return text
    try:
        return text.encode('latin-1').decode('utf-8')
    except Exception:
        return text


CATEGORIES = [
    ("pets", "Питомцы", 1), 
    ("eggs", "Яйца", 2), 
    ("potions", "Зелья", 3), 
    ("other", "Другое", 4)
]

PRODUCTS = [
    ("Демо-питомец «Лунный лис»", "pets", 250, "Тестовый товар для проверки магазина."),
    ("Демо-питомец «Сапфировый дракон»", "pets", 480, "Тестовый товар для проверки магазина."),
    ("Демо-яйцо «Звёздное»", "eggs", 90, "Тестовый товар для проверки магазина."),
    ("Демо-зелье «Полёт»", "potions", 60, "Тестовый товар для проверки магазина."),
    ("Демо-зелье «Неон»", "potions", 75, "Тестовый товар для проверки магазина."),
    ("Демо-набор «Новичок»", "other", 150, "Тестовый товар для проверки магазина."),
]

SETTINGS = {
    "shop_name": "ChapaShop",
    "shop_description": "Магазин товаров Adopt Me",
    "primary_color": "#7B2FF7",
    "maintenance_mode": "0",
    "contact_info": "Поддержка: @ChapikSupport",
    "order_rules": "После оплаты укажите верный Roblox username.",
    "bot_username": "",
}


def seed(db: Session) -> None:
    try:
        # 1. Берем все товары из базы и исправляем их названия
        products = db.scalars(select(Product)).all()
        if products and ("Ð" in products[0].name):
            for p in products:
                p.name = fix_encoding(p.name)
                p.description = fix_encoding(p.description)
        db.commit()

        # 2. Если в базе пусто — создаем новые
        if db.scalar(select(Product).limit(1)) is None:
            cats = {}
            for slug, name, order in CATEGORIES:
                c = Category(slug=slug, name=name, sort_order=order)
                db.add(c)
                db.flush()
                cats[slug] = c
            
            for name, slug, price, desc in PRODUCTS:
                db.add(Product(name=name, category_id=cats[slug].id, price_stars=price,
                               description=desc, is_demo=True))
        
        # 3. Заполняем настройки
        for k, v in {**SETTINGS, **BOT_TEXTS}.items():
            if db.get(Setting, k) is None:
                db.add(Setting(key=k, value=v))
        
        db.commit()
    except Exception as e:
        print("Ошибка при заполнении базы:", e)
        db.rollback()
