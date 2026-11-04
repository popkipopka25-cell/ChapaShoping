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

# ... (остальные обработчики и роуты оставляем как были, они не влияют на кодировку)
