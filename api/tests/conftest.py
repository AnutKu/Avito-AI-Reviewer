"""Общие фикстуры тестов.

Юнит-тесты балансировщика (`test_distribution.py`) БД не требуют.
Интеграционные тесты роутера методиста включаются только когда задан
`TEST_DATABASE_URL` — иначе они помечаются skipped. Пример:

    TEST_DATABASE_URL=postgresql+psycopg://avito:avito@localhost:55432/avito_ai_reviewer \
        python -m pytest
"""

import hashlib
import os

import pytest

_TEST_DB = os.environ.get("TEST_DATABASE_URL")
if _TEST_DB:
    # db.py читает DATABASE_URL при импорте — задаём до импорта приложения.
    os.environ["DATABASE_URL"] = _TEST_DB
    os.environ.setdefault("SEED_ON_START", "false")


@pytest.fixture(autouse=True)
def _offline_github(monkeypatch):
    """Тесты не ходят в GitHub: submit получает детерминированный снапшот."""

    if not _TEST_DB:
        return

    from app.routers import student
    from app.services.github import GithubSnapshot

    def _fake(source_url: str) -> GithubSnapshot:
        return GithubSnapshot(
            content=f"# demo snapshot\n\nИсточник: {source_url}\n",
            content_hash="test-" + hashlib.sha256(source_url.encode()).hexdigest()[:16],
            parsed_facts={"runs": 22, "metrics": ["accuracy", "f1"], "seed": 42, "mock": True},
        )

    monkeypatch.setattr(student, "fetch_github_snapshot", _fake)
    # фоновые AI-прогоны в тестах не нужны — они бы стучались в ai-reviewer и
    # тормозили. Сдача ставит в очередь оба: ревью и детекцию.
    monkeypatch.setattr(student, "run_review", lambda review_id: None)
    monkeypatch.setattr(student, "run_detection", lambda review_id: None)


@pytest.fixture
def client():
    if not _TEST_DB:
        pytest.skip("integration test: set TEST_DATABASE_URL to run")

    from fastapi.testclient import TestClient

    from app.db import SessionLocal, engine
    from app.main import app
    from app.models import Base
    from app.seed import seed_demo

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo(db)

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def methodist(client):
    token = client.post("/api/auth/demo/methodist").json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def reviewer(client):
    token = client.post("/api/auth/demo/reviewer").json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
