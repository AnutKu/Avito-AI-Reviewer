"""Каждый адрес, который зовёт кабинет, должен существовать в роутере.

Тест написан по следам живой ошибки: ручку `ai-fill` перенесли на сервере, а
вызов в редакторе остался по старому адресу — кнопка «Улучшить с AI» молча
отвечала «Not Found». Тесты роутера этого не ловят (ручка есть), тесты
интерфейса тоже (сеть замокана), поэтому шов проверяется отдельно.

Разбор нарочно текстовый: поднимать браузер ради списка адресов не нужно.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import app

UI_SRC = Path(__file__).resolve().parents[2] / "ui" / "src"

# Каждый вид кавычек закрывается своим же: внутри `${...}` шаблонной строки
# спокойно живут одинарные кавычки, и общий класс символов на них обрывался —
# вызов молча выпадал из проверки.
CALL = re.compile(r"""api\(\s*(?:'(/[^']+)'|"(/[^"]+)"|`(/[^`]+)`)""")

# Подстановки в шаблонной строке заменяем на заглушку пути: конкретное значение
# роутеру безразлично, важна форма адреса.
PLACEHOLDER = re.compile(r"\$\{[^}]*\}")


def ui_calls() -> set[str]:
    found: set[str] = set()
    for pattern in ("*.vue", "*.js"):
        for source in UI_SRC.rglob(pattern):
            for groups in CALL.findall(source.read_text(encoding="utf-8")):
                raw = next(filter(None, groups))
                found.add(PLACEHOLDER.sub("{}", raw).split("?")[0])
    return found


def route_paths() -> list[str]:
    return [
        route.path[4:]
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/")
    ]


def fits(call: str, route: str) -> bool:
    """Совпадают ли формы адресов.

    Сравнение посегментное: подстановка вроде `${action}` может стоять на месте
    не только параметра, но и литерала (`apply`/`reject`), поэтому «заглушка
    против литерала» разрешена. Но только одна на адрес: две таких натяжки
    подряд склеивали заведомо разные маршруты — так `assignments/{}/ai-fill`
    ложно совпадал с `assignments/draft-from-idea/{job_id}`.
    """

    left, right = call.strip("/").split("/"), route.strip("/").split("/")
    if len(left) != len(right):
        return False
    loose = 0
    for a, b in zip(left, right, strict=True):
        if a == b or (a == "{}" and b.startswith("{")):
            continue  # точное совпадение литералов или параметр на месте параметра
        if a == "{}" or b.startswith("{"):
            loose += 1
            continue
        return False
    return loose <= 1


@pytest.mark.parametrize("path", sorted(ui_calls()))
def test_every_path_the_cabinet_calls_exists(path):
    assert any(fits(path, route) for route in route_paths()), (
        f"кабинет зовёт {path}, а такого маршрута в API нет"
    )


def test_the_scan_actually_found_calls():
    """Защита от тихого нуля: сломанный разбор не должен выглядеть как успех."""

    calls = ui_calls()
    assert len(calls) > 20, f"нашлось всего {len(calls)} вызовов — разбор сломан"
    assert "/methodist/ai-fill" in calls


def test_no_route_is_bound_to_a_private_helper():
    """Декоратор обязан стоять на ручке, а не на функции над ней.

    Написан по следам живой ошибки: между `@router.post(.../complete)` и
    `complete` вклинился приватный `_penalty_preview`, декоратор сел на него, а
    настоящая ручка осталась незарегистрированной. Адрес при этом существовал —
    проверка выше его находила, — но вёл в помощника с нетипизированными
    аргументами, и публикация ревью отвечала 422 «Field required» по двум
    query-параметрам, которых кабинет и не думал слать.

    Правило простое и настоящее: имя с подчёркивания — не эндпоинт.
    """

    bound = [
        (route.path, route.endpoint.__name__)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/") and hasattr(route, "endpoint")
    ]
    private = [(path, name) for path, name in bound if name.startswith("_")]
    assert not private, f"маршруты смотрят в приватные функции: {private}"
