#!/usr/bin/env python3
"""Проверялка API task-creater: один прогон по основным эндпоинтам, вход → выход.

Только stdlib. Сервис должен быть поднят (`make up` / `make dev`).

    python3 scripts/probe.py
    python3 scripts/probe.py --idea "..." --track "Backend / Go" --rounds 2
    BASE_URL=http://localhost:8000 python3 scripts/probe.py --full --save ./probe-out

Что смотреть, чтобы судить о качестве:
  • раздел 1 — сгенерированные критерии: проверяемые ли, не субъективные ли, суммируются ли в разбалловку;
  • раздел 2 — spread в матрице оценок (max−min по критерию): большой spread = критерий, скорее всего, неоднозначен;
             — находки критика: обоснованы ли, к тем ли критериям;
             — правки «было → стало»: снимают ли реальную проблему;
  • раздел 4 — финальная рубрика после правок.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_IDEA = (
    "Научить студентов писать конкурентный код на Go: пул воркеров, который разбирает "
    "задачи из очереди, с graceful shutdown по сигналу и ограничением на число "
    "одновременно выполняемых задач."
)

TTY = sys.stdout.isatty()
ARGS: argparse.Namespace = argparse.Namespace()


def _c(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if TTY else s


def bold(s):  # noqa: D401
    return _c(s, "1")


def dim(s):
    return _c(s, "2")


def green(s):
    return _c(s, "32")


def red(s):
    return _c(s, "31")


def yellow(s):
    return _c(s, "33")


# --------------------------------------------------------------------------- #
#  HTTP
# --------------------------------------------------------------------------- #

# Игнорируем *_proxy из окружения — это локальный сервис, прокси только мешает.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _parse(raw: bytes):
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw.decode("utf-8", "replace")


def call(method: str, path: str, body: dict | None = None, *, retries: int = 3):
    url = ARGS.base_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    t0 = time.perf_counter()
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with _OPENER.open(req, timeout=180) as r:
                return r.status, time.perf_counter() - t0, _parse(r.read())
        except urllib.error.HTTPError as e:  # это валидный ответ, не ретраим
            return e.code, time.perf_counter() - t0, _parse(e.read())
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last_err = getattr(e, "reason", e) or e
            if attempt < retries:
                time.sleep(1.0)
    print(red(f"! не достучался до {url}: {last_err}"))
    print(dim("  • сервис поднят?           make up  /  make dev"))
    print(dim("  • другой адрес/порт?       --base-url http://127.0.0.1:8000"))
    print(dim("  • контейнер перезапущен?   подождите healthcheck и повторите"))
    sys.exit(1)


def _trim(obj, limit: int):
    if not limit:
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + f"… (+{len(obj) - limit} симв.)"
    if isinstance(obj, list):
        return [_trim(x, limit) for x in obj]
    if isinstance(obj, dict):
        return {k: _trim(v, limit) for k, v in obj.items()}
    return obj


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + ln for ln in str(text).splitlines())


def show(method: str, path: str, body, status, dt, resp) -> None:
    ok = 200 <= status < 300
    tag = green(str(status)) if ok else red(str(status))
    print()
    print(bold(f"▶ {method} {path}") + dim(f"   → {status}") + f" {tag}" + dim(f"  {dt:.2f}s"))
    if body is not None:
        print(dim("  REQUEST"))
        print(_indent(json.dumps(body, ensure_ascii=False, indent=2)))
    print(dim("  RESPONSE"))
    limit = 0 if ARGS.full else 700
    if isinstance(resp, str):
        print(_indent(resp))
    else:
        print(_indent(json.dumps(_trim(resp, limit), ensure_ascii=False, indent=2)))


def save(name: str, obj) -> None:
    if not ARGS.save:
        return
    os.makedirs(ARGS.save, exist_ok=True)
    with open(os.path.join(ARGS.save, name), "w", encoding="utf-8") as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)


def hr(title: str) -> None:
    print("\n" + bold("═" * 78) + "\n" + bold(title) + "\n" + bold("═" * 78))


# --------------------------------------------------------------------------- #
#  Разделы
# --------------------------------------------------------------------------- #


def section_meta() -> None:
    hr("0. Сервис жив, справочники")
    st, dt, resp = call("GET", "/healthz")
    show("GET", "/healthz", None, st, dt, resp)
    if st != 200 or not isinstance(resp, dict) or resp.get("status") != "ok":
        print(red("сервис нездоров — дальше нет смысла"))
        sys.exit(1)
    if resp.get("llm_fake"):
        print(
            yellow(
                "  ⚠ LLM_FAKE=1 — ответы это детерминированные заглушки; о качестве МОДЕЛЕЙ по ним не судить"
            )
        )
    st, dt, resp = call("GET", "/personas")
    show("GET", "/personas", None, st, dt, resp)


def _digest_task(data: dict, total_points_declared) -> None:
    print("\n" + bold("  ── ЧТО ВИДИТ СТУДЕНТ ──"))
    if data.get("context_md", "").strip():
        print(dim("  контекст: " + data["context_md"][:400].replace("\n", " ")))
    print(dim("  задача  : " + data["statement_md"][:400].replace("\n", " ")))
    for i, d in enumerate(data.get("deliverables") or [], 1):
        print(f"    {i}. {d}")
    if data.get("public_rubric_note", "").strip():
        print(dim("  разбалловка (публично): " + data["public_rubric_note"][:300]))
    print(
        dim(
            "  публичная рубрика: "
            + " | ".join(
                f"{c['title']} (0–{c['max_points']}): {c.get('student_hint') or '—'}"
                for c in data["criteria"]
            )
        )
    )

    print("\n" + bold("  ── СКРЫТО ОТ СТУДЕНТА (рубрика ревьюера) ──"))
    total = 0.0
    for cr in data["criteria"]:
        total += cr["max_points"]
        kind = cr["check_kind"]
        kind_s = green(kind) if kind == "objective" else yellow(kind)
        print(f"  • {bold(cr['key'])}  {cr['max_points']} б.  [{kind_s}]  {cr['title']}")
        print(dim(f"      проверяем: {cr['description']}"))
        for s in cr.get("expected_signals") or []:
            print(dim(f"      сигнал:   {s}"))
        for lvl in cr.get("rubric_levels") or []:
            print(dim(f"        {lvl['points']} — {lvl['label']}: {lvl['descriptor']}"))
    flag = "" if abs(total - float(total_points_declared)) < 1e-6 else red("  ← не совпало!")
    print(f"  сумма весов: {round(total, 2)}  (заявлено {total_points_declared}){flag}")
    subj = [c["key"] for c in data["criteria"] if c["check_kind"] == "subjective"]
    if subj:
        print(yellow(f"  субъективных критериев: {len(subj)} — {', '.join(subj)}"))

    # утечка: student_hint не должен раскрывать конкретные ожидания
    # эвристика утечки: подсказка длинная И содержит конкретику (цифры/перечисление)
    def _leaky(h: str) -> bool:
        h = h or ""
        return len(h) > 120 and any(ch.isdigit() for ch in h)

    leaky = [c["key"] for c in data["criteria"] if _leaky(c.get("student_hint", ""))]
    if leaky:
        print(red(f"  ⚠ student_hint с конкретикой (риск утечки грейдинга): {', '.join(leaky)}"))


def section_generate() -> dict:
    hr("1. Генерация задания из идеи   POST /tasks/generate")
    body = {
        "idea": {
            "idea": ARGS.idea,
            "track": ARGS.track,
            "task_format": ARGS.format,
            "audience_level": ARGS.level,
            "total_points": ARGS.points,
            "delivery_channel": ARGS.channel,
            "language": "ru",
            "constraints": ARGS.constraints,
        }
    }
    st, dt, resp = call("POST", "/tasks/generate", body)
    show("POST", "/tasks/generate", body, st, dt, resp)
    save("01_generate.json", resp)
    if st != 201:
        print(red("генерация не удалась — стоп"))
        sys.exit(1)
    _digest_task(resp["data"], resp["total_points"])
    return resp


def _matrix(matrix: dict) -> None:
    personas = sorted({p for row in matrix.values() for p in row})
    kw = max([len(k) for k in matrix] + [12])
    header = " " * (kw + 4) + "".join(f"{p[:16]:>17}" for p in personas) + "     spread"
    print(dim(header))
    for key, row in matrix.items():
        vals = [row.get(p) for p in personas]
        cells = "".join(f"{('—' if v is None else format(v, '.2f')):>17}" for v in vals)
        present = [v for v in vals if v is not None]
        spread = (max(present) - min(present)) if len(present) > 1 else 0.0
        s_txt = f"{spread:.2f}"
        s_col = red(s_txt) if spread >= 1.0 else (yellow(s_txt) if spread >= 0.5 else s_txt)
        print(f"    {key:<{kw}}{cells}     {s_col}")


def _digest_validation(res: dict) -> None:
    print("\n" + bold("  ── ИТОГ ВАЛИДАЦИИ ──"))
    print(f"  converged: {green('да') if res['converged'] else yellow('нет')}")
    print(f"  summary:   {res['summary']}")
    m = res["metrics"]
    print(
        dim(
            f"  метрики:   вызовов LLM {m['llm_calls']}, токенов {m['total_tokens']} "
            f"(in {m['prompt_tokens']} / out {m['completion_tokens']}), ≈{m['cost_rub']} ₽, "
            f"{m['duration_s']}s, fast={m['model_fast']} smart={m['model_smart']}"
        )
    )

    for rd in res["rounds"]:
        print(
            "\n"
            + bold(
                f"  Раунд {rd['round_no']} — оценки по критериям × профиль "
                f"(spread = max−min; ≥1.00 подсвечен — вероятно неоднозначный критерий):"
            )
        )
        _matrix(rd["score_matrix"])

        if rd["findings"]:
            print(bold(f"\n  Раунд {rd['round_no']} — находки критика:"))
            for f in rd["findings"]:
                sev = {"high": red, "medium": yellow}.get(f["severity"], dim)
                tgt = f.get("target", "rubric")
                tgt_s = red("BRIEF") if tgt == "brief" else dim("rubric")
                print(
                    f"    {sev('[' + f['severity'] + ']')} {f['kind']:<16} {tgt_s} "
                    f"{f['criterion_key'] or '— (уровень задания)'}"
                )
                print(dim(f"        {f['explanation']}"))
                if f.get("fix_suggestion"):
                    print(dim(f"        как чинить: {f['fix_suggestion']}"))
                print(dim(f"        основание: {f['evidence']}"))

        amb = [(s["persona"], a) for s in rd["solutions"] for a in (s.get("exploited_ambiguities") or [])]
        if amb:
            print(bold(f"\n  Раунд {rd['round_no']} — где решателям не хватило брифа:"))
            for persona, a in amb:
                print(dim(f"        {persona}: {a}"))

    print("\n" + bold("  ── ПРЕДЛОЖЕННЫЕ ПРАВКИ (идут в /decisions) ──"))
    if not res["proposed_edits"]:
        print("    нет — рубрика сошлась без правок")
    for e in res["proposed_edits"]:
        sev = {"high": red, "medium": yellow}.get(e["severity"], dim)
        print(
            f"\n    {bold(e['id'])}  {e['operation'].upper()}  {e['criterion_key']}  "
            f"{sev('severity=' + e['severity'])}  addresses={e['addresses']}"
        )
        if e.get("before_snapshot"):
            print(dim(f"        было:  {e['before_snapshot']}"))
        if e.get("proposed_criterion"):
            print(green(f"        стало: {e['proposed_criterion']['description']}"))
        print(dim(f"        почему: {e['rationale']}"))


def section_validate(task: dict) -> str:
    hr("2. Валидация критериев агентами   POST /tasks/{id}/validate")
    tid = task["id"]
    body = {"max_rounds": ARGS.rounds}
    st, dt, resp = call("POST", f"/tasks/{tid}/validate", body)
    show("POST", f"/tasks/{tid}/validate", body, st, dt, resp)
    if st != 202:
        print(red("прогон не стартовал — стоп"))
        sys.exit(1)
    rid = resp["id"]

    print("\n" + dim("  … жду завершения  (poll GET /validation-runs/{id})"))
    last = None
    deadline = time.time() + 300
    run: dict = {}
    while time.time() < deadline:
        _, _, run = call("GET", f"/validation-runs/{rid}")
        if run.get("progress") != last:
            last = run.get("progress")
            print(f"    [{run['status']}] {last}")
        if run["status"] in ("succeeded", "failed"):
            break
        time.sleep(1.5)
    save("04_validation_run.json", run)

    if run.get("status") != "succeeded":
        print(red(f"\nпрогон завершился со статусом: {run.get('status')}"))
        print(_indent(run.get("error") or "(без деталей)"))
        sys.exit(1)

    if ARGS.raw:
        show("GET", f"/validation-runs/{rid}", None, 200, 0.0, run)
    _digest_validation(run["result"])
    return rid


def section_decisions(rid: str, task: dict) -> dict:
    hr("3. Решение человека: принять все правки   POST /validation-runs/{id}/decisions")
    _, _, run = call("GET", f"/validation-runs/{rid}")
    edits = run["result"]["proposed_edits"]
    if not edits:
        print("    правок нет — раздел пропущен")
        return task
    body = {"decisions": [{"edit_id": e["id"], "accept": True} for e in edits], "author": "probe"}
    st, dt, resp = call("POST", f"/validation-runs/{rid}/decisions", body)
    show("POST", f"/validation-runs/{rid}/decisions", body, st, dt, resp)
    save("05_revised_task.json", resp)
    if st != 200:
        print(red("применение правок не удалось"))
        return task
    print(
        green(
            f"\n  → задание v{resp['version']}  (source={resp['source']})  критериев: {len(resp['data']['criteria'])}"
        )
    )
    for cr in resp["data"]["criteria"]:
        print(f"    • {cr['key']}  {cr['max_points']} б.  — {cr['description'][:140]}")
    return resp


def section_export(task: dict) -> None:
    hr("4. Экспорт финальной версии   GET /tasks/{id}/export?view=student|reviewer")
    tid = task["id"]

    st, dt, sj = call("GET", f"/tasks/{tid}/export?format=json&view=student")
    show("GET", f"/tasks/{tid}/export?format=json&view=student", None, st, dt, sj)
    save("06_export_student.json", sj)
    leaked = [k for k in ("reference_solution_md", "common_mistakes", "reviewer_notes") if k in (sj or {})]
    crit_leak = any(
        (c.get("description") or c.get("expected_signals")) for c in (sj or {}).get("criteria", [])
    )
    if leaked or crit_leak:
        print(red(f"  ⚠ студенческий JSON содержит скрытое: {leaked or 'детали критериев'}"))
    else:
        print(green("  студенческий JSON без скрытых полей ✓"))

    st, dt, rj = call("GET", f"/tasks/{tid}/export?format=json&view=reviewer")
    save("06_export_reviewer.json", rj)

    st, dt, md = call("GET", f"/tasks/{tid}/export?format=markdown&view=student")
    text = md if isinstance(md, str) else json.dumps(md, ensure_ascii=False)
    if not ARGS.full and len(text) > 2500:
        text = text[:2500] + f"\n… (+{len(text) - 2500} симв.; полностью — с --full)"
    print()
    print(bold(f"▶ GET /tasks/{tid}/export?format=markdown&view=student") + dim(f"   {st}  {dt:.2f}s"))
    print(_indent(text))
    save("06_export_student.md", md if isinstance(md, str) else "")

    _, _, rmd = call("GET", f"/tasks/{tid}/export?format=markdown&view=reviewer")
    save("06_export_reviewer.md", rmd if isinstance(rmd, str) else "")


def section_versions(task: dict) -> None:
    hr("5. История версий   PATCH /tasks/{id}  +  GET /tasks/{root_id}/versions")
    new_title = task["data"]["title"] + " (probe patch)"
    st, dt, resp = call("PATCH", f"/tasks/{task['id']}", {"title": new_title})
    brief = {"version": resp.get("version"), "source": resp.get("source")} if st == 200 else resp
    show("PATCH", f"/tasks/{task['id']}", {"title": new_title}, st, dt, brief)

    st, dt, resp = call("GET", f"/tasks/{task['root_id']}/versions")
    rows = (
        [
            {"version": r["version"], "source": r["source"], "total_points": r["total_points"], "id": r["id"]}
            for r in resp
        ]
        if st == 200
        else resp
    )
    show("GET", f"/tasks/{task['root_id']}/versions", None, st, dt, rows)


# --------------------------------------------------------------------------- #


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser(description="probe task-creater API: вход → выход по основным эндпоинтам")
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--idea", default=DEFAULT_IDEA, help="идея задания своими словами")
    ap.add_argument("--track", default="Backend / Go", help="направление курса")
    ap.add_argument(
        "--format",
        default="auto",
        choices=["auto", "case_study", "metrics_design", "coding", "open"],
        help="формат задания",
    )
    ap.add_argument("--channel", default="github", choices=["github", "stepik", "gdocs", "other"])
    ap.add_argument("--level", default="intermediate", choices=["novice", "intermediate", "advanced"])
    ap.add_argument("--points", type=float, default=10, help="желаемая разбалловка")
    ap.add_argument(
        "--constraints",
        default="Обязательны юнит-тесты. Штраф за просрочку: -1 балл в сутки, максимум -3.",
    )
    ap.add_argument("--rounds", type=int, default=2, help="max_rounds валидации")
    ap.add_argument("--full", action="store_true", help="не обрезать длинные поля")
    ap.add_argument("--raw", action="store_true", help="дампить полный JSON прогона валидации")
    ap.add_argument("--save", metavar="DIR", help="сохранить полные ответы в каталог")
    ARGS = ap.parse_args()

    print(dim(f"base_url = {ARGS.base_url}"))
    print(dim(f"идея     = {ARGS.idea}"))
    print(
        dim(
            f"трек     = {ARGS.track}   уровень = {ARGS.level}   баллы = {ARGS.points}   раундов = {ARGS.rounds}"
        )
    )

    section_meta()
    task = section_generate()

    st, dt, echoed = call("GET", f"/tasks/{task['id']}")
    show(
        "GET",
        f"/tasks/{task['id']}",
        None,
        st,
        dt,
        {k: echoed.get(k) for k in ("id", "root_id", "version", "source", "idea_id")}
        if isinstance(echoed, dict)
        else echoed,
    )

    rid = section_validate(task)
    revised = section_decisions(rid, task)
    section_export(revised)
    section_versions(revised)

    print("\n" + green("готово."))
    if ARGS.save:
        print(dim(f"полные ответы сохранены в {ARGS.save}/"))


if __name__ == "__main__":
    main()
