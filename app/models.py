"""Все таблицы ChapaShop. Изменения схемы — только через миграции Alembic."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer,
                        JSON, String, Text, UniqueConstraint, CheckConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

def now():
    return datetime.now(timezone.utc)

class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    refunded = "refunded"
    failed = "failed"

class OrderStatus(str, enum.Enum):
    awaiting_payment = "awaiting_payment"
    paid = "paid"
    processing = "processing"
    awaiting_delivery = "awaiting_delivery"
    delivered = "delivered"
    rejected = "rejected"
    refunded = "refunded"

ORDER_STATUS_RU = {
    "awaiting_payment": "Ожидает оплаты", "paid": "Оплачен", "processing": "В обработке",
    "awaiting_delivery": "Ожидает выдачи", "delivered": "Выдан", "rejected": "Отклонён",
    "refunded": "Возврат оформлен",
}

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    roblox_username: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    products: Mapped[list["Product"]] = relationship(back_populates="category")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=10)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Product(Base):
    __tablename__ = "products"
    # Разрешаем 0 звезд
    __table_args__ = (CheckConstraint("price_stars >= 0", name="ck_price_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(512))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    price_stars: Mapped[int] = mapped_column(Integer)
    old_price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True) # Для скидок
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    category: Mapped[Category | None] = relationship(back_populates="products")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    roblox_username: Mapped[str] = mapped_column(String(32), index=True)
    total_stars: Mapped[int] = mapped_column(Integer)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, native_enum=False), default=PaymentStatus.pending)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, native_enum=False), default=OrderStatus.awaiting_payment, index=True)
    server_link: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")
    history: Mapped[list["OrderStatusHistory"]] = relationship(cascade="all, delete-orphan")

    @property
    def number(self) -> str:
        # Красивый номер (например, A-1234)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        char = alphabet[self.id % 24]
        num = (self.id * 7391) % 10000
        return f"{char}-{num:04d}"

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    product_name: Mapped[str] = mapped_column(String(128))
    price_stars: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255), unique=True)
    amount_stars: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="XTR")
    status: Mapped[str] = mapped_column(String(32), default="succeeded")
    raw: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    old_status: Mapped[str | None] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[str] = mapped_column(String(64), default="system")
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
