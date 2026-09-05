"""Чем наполняется кабинет на старте.

Эта развилка уже один раз тихо сделала не то: на сервере после обновления
осталась старая база, потому что файл с разборами не попал в образ, и старт
молча откатился на демонстрационный сев. Молча — ключевое слово, поэтому здесь
проверяется не только выбор, но и то, что у каждого исхода есть внятная причина.

БД не нужна: развилка принимает решение по содержимому сессии, которую здесь
подменяют заглушкой.
"""

import pytest

from app import real_course_loader as loader


class FakeSession:
    """Ровно столько от Session, сколько читает `prepare`."""

    def __init__(self, *, courses=(), demo_untouched=False):
        self._courses = list(courses)
        self.demo_untouched = demo_untouched
        self.wiped = False
        self.restored = False

    def scalar(self, *_args, **_kwargs):
        return self._courses[0] if self._courses else None


@pytest.fixture
def stub(monkeypatch):
    class FakeFile:
        """Путь подменяется целиком: у PosixPath метод exists не переопределить."""

        def __init__(self, present):
            self.present = present

        def exists(self):
            return self.present

        def __str__(self):
            return "data/real_course/ai_results.json"

    def apply(session, *, results_exist=True, loaded=False):
        monkeypatch.setattr(loader, "RESULTS", FakeFile(results_exist))
        monkeypatch.setattr(loader, "is_loaded", lambda db: loaded)
        monkeypatch.setattr(loader, "demo_is_untouched", lambda db: db.demo_untouched)

        def wipe(db):
            db.wiped = True

        def restore(db, **_kwargs):
            db.restored = True
            return {"works": 33, "reviews": 33, "closed": 24, "accepted": 102, "changed": 36}

        monkeypatch.setattr(loader, "wipe", wipe)
        monkeypatch.setattr(loader, "restore", restore)
        return session

    return apply


def test_empty_database_is_filled_from_the_repository(stub):
    session = stub(FakeSession())
    outcome = loader.prepare(session)
    assert outcome["action"] == "loaded"
    assert outcome["works"] == 33
    assert session.restored and not session.wiped


def test_untouched_demo_course_is_replaced(stub):
    """Демо-курс целиком создан севом — заменить его не значит потерять данные."""

    session = stub(FakeSession(courses=["демо"], demo_untouched=True))
    outcome = loader.prepare(session)
    assert outcome["action"] == "loaded"
    assert session.wiped and session.restored


def test_hand_made_content_is_never_wiped_on_start(stub):
    """Заведённое человеком задание — чужая работа, и её судьбу решает человек."""

    session = stub(FakeSession(courses=["чужой курс"], demo_untouched=False))
    outcome = loader.prepare(session)
    assert outcome["action"] == "kept"
    assert not session.wiped and not session.restored


def test_refusal_tells_how_to_do_it_anyway(stub):
    session = stub(FakeSession(courses=["чужой курс"], demo_untouched=False))
    assert "load_real_course" in loader.prepare(session)["reason"]


def test_already_loaded_course_is_left_alone(stub):
    session = stub(FakeSession(courses=["настоящий"]), loaded=True)
    outcome = loader.prepare(session)
    assert outcome["action"] == "kept"
    assert not session.wiped and not session.restored


def test_missing_results_file_is_named_as_the_reason(stub):
    """Именно этот случай и был на сервере: файла нет, потому что нет в образе."""

    session = stub(FakeSession(), results_exist=False)
    outcome = loader.prepare(session)
    assert outcome["action"] == "skipped"
    assert "образ" in outcome["reason"]


def test_flag_off_is_reported_as_a_deliberate_choice(stub):
    session = stub(FakeSession())
    outcome = loader.prepare(session, enabled=False)
    assert outcome["action"] == "skipped"
    assert "флаг" in outcome["reason"]
    assert not session.restored


def test_every_outcome_explains_itself(stub):
    for session, kwargs in (
        (stub(FakeSession()), {}),
        (stub(FakeSession(courses=["ч"])), {}),
        (stub(FakeSession(), results_exist=False), {}),
        (stub(FakeSession()), {"enabled": False}),
    ):
        assert loader.prepare(session, **kwargs)["reason"].strip()
