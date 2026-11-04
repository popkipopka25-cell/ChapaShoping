from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
    return engine


engine = make_engine(get_settings().db_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_database():
    """Полностью удаляет все таблицы и создает их заново."""
    try:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        print("База данных успешно очищена и создана заново.")
    except Exception as e:
        print(f"Ошибка при сбросе базы: {e}")
