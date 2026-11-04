"""Точка входа ChapaShop: uvicorn main:app"""
from contextlib import asynccontextmanager
from pathlib import Path

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, catalog, health, miniapp, telegram
from app.db import SessionLocal
from app.seed import seed

WEB = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        from app.db import Base, engine
        Base.metadata.create_all(engine)
        
        seed(db)
        admin.ensure_owner(db)
    from bot.handlers import setup_bot
    setup_bot()
    from app.preflight import run_checks, summary
    res = summary(run_checks())
    if res["blockers"]:
        logging.getLogger("chapashop").error("Предстартовая проверка: не настроено %s", res["blockers"])
    yield


app = FastAPI(title="ChapaShop", lifespan=lifespan)
app.include_router(health.router)
app.include_router(catalog.router)
app.include_router(telegram.router)
app.include_router(miniapp.router)
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


log = logging.getLogger("chapashop")
MAX_BODY = 1 * 1024 * 1024          
MAX_BODY_RESTORE = 50 * 1024 * 1024  

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.error("Ошибка %s на %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse({"detail": "Внутренняя ошибка сервера. Попробуйте позже."}, status_code=500)


@app.exception_handler(RequestValidationError)
async def bad_input(request: Request, exc: RequestValidationError):
    errs = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse({"detail": errs}, status_code=422)


@app.middleware("http")
async def security_headers(request, call_next):
    limit = MAX_BODY_RESTORE if request.url.path == "/admin/api/restore" else MAX_BODY
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
    try:
        resp = await call_next(request)
    except Exception as exc:
        return await unhandled(request, exc)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    if not request.url.path.startswith("/docs"):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; "
            "connect-src 'self'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; "
            "object-src 'none'; base-uri 'self'")
    if request.url.path.startswith("/admin"):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(WEB / "admin.html")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


@app.get("/product/{product_id}", include_in_schema=False)
@app.get("/cart", include_in_schema=False)
@app.get("/about", include_in_schema=False)
@app.get("/app", include_in_schema=False)
@app.get("/orders", include_in_schema=False)
@app.get("/orders/{order_id}", include_in_schema=False)
@app.get("/profile", include_in_schema=False)
def spa_pages(product_id: int | None = None, order_id: int | None = None):
    return FileResponse(WEB / "index.html")
