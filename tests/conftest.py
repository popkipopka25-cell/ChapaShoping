import os
os.environ["DATABASE_URL"] = "sqlite:///./test_chapashop.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
import app.models  # noqa


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from main import app
    from app.api import miniapp
    miniapp._hits.clear()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _no_real_uploads(monkeypatch):
    """Файлы в тестах никогда не уходят в настоящий Telegram — только в OUTBOX."""
    import bot.telegram as bt

    def fake(chat_id, filename, content, caption=None):
        bt.OUTBOX.append({"method": "sendDocument", "chat_id": chat_id, "filename": filename,
                          "size": len(content), "caption": caption})
        return True
    monkeypatch.setattr(bt, "send_document", fake)
