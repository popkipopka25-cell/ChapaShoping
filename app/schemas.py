from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    image_url: str | None
    category_id: int | None
    price_stars: int
    old_price_stars: int | None
    is_available: bool
    is_demo: bool


class CartLineIn(BaseModel):
    product_id: int
    quantity: int


class CartQuoteIn(BaseModel):
    items: list[CartLineIn]
    promo_code: str | None = None # Добавили промокод


class CartLineOut(BaseModel):
    product_id: int
    name: str
    price_stars: int
    old_price_stars: int | None
    quantity: int
    subtotal: int
    available: bool


class CartQuoteOut(BaseModel):
    items: list[CartLineOut]
    total_stars: int
    discount_amount: int # Сколько скинули
    promo_applied: bool
    count: int
    removed: list[int]
