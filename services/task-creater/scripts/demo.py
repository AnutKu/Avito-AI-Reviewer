"""Сквозной сценарий: идея → задание с критериями → валидация агентами →
предложенные правки → решение человека → финальная рубрика.

Запуск против поднятого сервиса:
    uv run python scripts/demo.py
    BASE_URL=http://127.0.0.1:8000 uv run python scripts/demo.py
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")

IDEA = {
    "idea": (
        "Хочу задание, на котором студенты научатся писать конкурентный код на Go: "
        "пул воркеров, который обрабатывает задачи из очереди, с graceful shutdown по "
        "сигналу и ограничением на число одновременно выполняемых задач."
    ),
    "track": "Backend / Go",
    "audience_level": "intermediate",
    "target_effort_hours": 6,
    "delivery_channel": "github",
    "language": "ru",
    "total_points": 10,
    "constraints": "Обязательны юнит-тесты. Штраф за просрочку: -1 балл за каждые сутки, максимум -3.",
}


def _hr(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def main() -> int:
    c = httpx.Client(base_url=BASE_URL, timeout=120, trust_env=False)

    print(f"health: {c.get('/healthz').json()}")

    _hr("1. Генерация задания из идеи")
    task = c.post("/tasks/generate", json={"idea": IDEA}).json()
    task_id = task["id"]
    print(f"task_id={task_id} v{task['version']}  «{task['data']['title']}»")
    print(f"итого баллов: {task['total_points']}")
    for cr in task["data"]["criteria"]:
        print(f"  - [{cr['max_points']:>4}] {cr['key']:<22} {cr['check_kind']:<10} {cr['title']}")

    _hr("2. Запуск валидации критериев (мультиагент)")
    run = c.post(f"/tasks/{task_id}/validate", json={"max_rounds": 2}).json()
    run_id = run["id"]
    print(f"run_id={run_id} status={run['status']}")

    while True:
        run = c.get(f"/validation-runs/{run_id}").json()
        print(f"  … {run['status']}: {run['progress']}")
        if run["status"] in ("succeeded", "failed"):
            break
        time.sleep(1.0)

    if run["status"] == "failed":
        print("ПРОГОН УПАЛ:\n", run["error"])
        return 1

    res = run["result"]
    _hr("3. Что нашли агенты")
    print(res["summary"])
    print(f"\nМетрики: {res['metrics']}")

    for rd in res["rounds"]:
        print(f"\n— Раунд {rd['round_no']} — расхождение оценок по критериям (balls by persona):")
        for key, row in rd["score_matrix"].items():
            cells = "  ".join(f"{p}={v}" for p, v in row.items())
            print(f"    {key:<22} {cells}")

    print("\nНаходки:")
    for rd in res["rounds"]:
        for f in rd["findings"]:
            print(f"  [{f['severity']:<6}] {f['kind']:<20} {f['criterion_key']}: {f['explanation']}")

    _hr("4. Предложенные правки критериев (относительно исходной рубрики)")
    edits = res["proposed_edits"]
    for e in edits:
        print(f"\n  {e['id']} {e['operation'].upper()} {e['criterion_key']}  (severity={e['severity']})")
        print(f"    было:  {e['before_snapshot']}")
        if e["proposed_criterion"]:
            print(f"    стало: {e['proposed_criterion']['description']}")
        print(f"    почему: {e['rationale']}")

    if not edits:
        print("  правок нет — рубрика сошлась")

    _hr("5. Решение человека: принимаем все правки")
    decisions = {
        "decisions": [{"edit_id": e["id"], "accept": True} for e in edits],
        "author": "demo",
    }
    new_task = c.post(f"/validation-runs/{run_id}/decisions", json=decisions).json()
    print(f"новая версия задания: v{new_task['version']} (source={new_task['source']})")
    for cr in new_task["data"]["criteria"]:
        print(f"  - [{cr['max_points']:>4}] {cr['key']:<22} {cr['title']}")

    _hr("6. Экспорт финального задания (Markdown)")
    md = c.get(f"/tasks/{new_task['id']}/export", params={"format": "markdown"}).text
    print(md[:2000] + ("\n… (обрезано)" if len(md) > 2000 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
