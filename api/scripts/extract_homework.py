"""Разовое извлечение текста реальных ДЗ в `api/data/real_course/`.

Условия и решения кейсодатель передал в пяти форматах: markdown, Word, Excel,
PDF и выгрузки ноутбуков. Разбирать их при каждом запуске кабинета незачем и
вредно: загрузка курса зависела бы от того, установлена ли на машине библиотека
для PDF, а содержимое базы — от её версии. Поэтому текст извлекается один раз,
кладётся рядом с кодом и дальше читается как обычный markdown.

    python -m scripts.extract_homework

Единственная зависимость сверх рантайма — `pypdf`, и она нужна только здесь.

Из условия вырезается раздел «Критерии оценивания»: в кабинете шкала живёт
отдельной сущностью (рубрикой), и держать её вторым экземпляром внутри текста
задания — верный способ развести их со временем.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.real_course import HOMEWORK_ROOT, TASKS  # noqa: E402

SOURCE = ROOT.parent / HOMEWORK_ROOT
TARGET = ROOT / "data" / "real_course"

# Заголовок раздела со шкалой. В условиях он пишется по-разному — «Критерии
# оценивания», «Критерии оценки», «Критерий оценки», — и в Word'е перед ним
# нередко стоит эмодзи или маркер списка, поэтому начало строки допускает
# несколько не-буквенных символов.
CRITERIA_HEADING = re.compile(r"^[^\wА-Яа-я]{0,4}критери\w*\s+оцен", re.I | re.M)


# --------------------------------------------------------------------------- #
#  Форматы
# --------------------------------------------------------------------------- #


def from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>|</w:tr>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", xml))


def from_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            raw = archive.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
            shared = [
                htmlmod.unescape(re.sub(r"<[^>]+>", "", chunk))
                for chunk in re.findall(r"<si>(.*?)</si>", raw, re.S)
            ]
        rows: list[str] = []
        sheets = sorted(n for n in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
        for name in sheets:
            sheet = archive.read(name).decode("utf-8", "ignore")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
                cells = []
                for kind, body in re.findall(r"<c[^>]*?(?:\s+t=\"(\w+)\")?[^>]*>(.*?)</c>", row, re.S):
                    value = re.search(r"<v>(.*?)</v>", body, re.S)
                    if not value:
                        inline = re.search(r"<is>(.*?)</is>", body, re.S)
                        cells.append(
                            htmlmod.unescape(re.sub(r"<[^>]+>", "", inline.group(1))) if inline else ""
                        )
                        continue
                    raw = value.group(1)
                    cells.append(
                        shared[int(raw)]
                        if kind == "s" and raw.isdigit() and int(raw) < len(shared)
                        else raw
                    )
                if any(cell.strip() for cell in cells):
                    rows.append(" | ".join(cells))
        return "\n".join(rows)


def from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    pages = PdfReader(str(path)).pages
    # В экспортах из досок между буквами стоят пробелы — «т е к с т». Склеиваем
    # только их, не трогая нормальные слова.
    text = "\n".join((page.extract_text() or "") for page in pages)
    return re.sub(r"(?<=\b\w) (?=\w\b)", "", text)


def from_html(path: Path) -> str:
    text = path.read_text("utf-8", errors="ignore")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br[^>]*>|</(p|div|tr|h\d|li|pre)>", "\n", text, flags=re.I)
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", text))


def from_ipynb(path: Path) -> str:
    notebook = json.loads(path.read_text("utf-8", errors="ignore"))
    parts = []
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        parts.append(source if cell.get("cell_type") == "markdown" else f"```python\n{source}\n```")
    return "\n\n".join(parts)


READERS = {
    ".docx": from_docx,
    ".xlsx": from_xlsx,
    ".pdf": from_pdf,
    ".html": from_html,
    ".htm": from_html,
    ".ipynb": from_ipynb,
    ".md": lambda path: path.read_text("utf-8", errors="ignore"),
    ".txt": lambda path: path.read_text("utf-8", errors="ignore"),
}


# Управляющие символы. NUL приходит из PDF и роняет вставку в postgres, а
# остальные всё равно не несут смысла в тексте работы.
# Управляющие и невидимые символы: NUL приходит из PDF и роняет вставку в
# postgres, а нулевой ширины пробелы из Word ломают разбор заголовков — строка
# выглядит начинающейся со слова, а на самом деле начинается с пустоты.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\ufe0e\ufe0f\ufeff]")


def tidy(text: str) -> str:
    text = CONTROL.sub("", text.replace("\xa0", " ").replace("\r\n", "\n"))
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.rstrip() for line in text.split("\n")]
    # Экспорты из онлайн-досок повторяют подпись автора и водяной знак после
    # каждой карточки — сотни одинаковых строк подряд. Смысла в них нет, а
    # место в контексте модели они занимают настоящее.
    collapsed: list[str] = []
    for line in lines:
        if line.strip() and collapsed and collapsed[-1] == line:
            continue
        collapsed.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(collapsed)).strip()


def read(path: Path) -> str:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"нет читателя для {path.suffix}")
    return tidy(reader(path))


def strip_criteria(text: str) -> str:
    found = CRITERIA_HEADING.search(text)
    return text[: found.start()].strip() if found else text


def header(source: Path, note: str = "") -> str:
    return (
        f"<!-- Извлечено из {source.relative_to(ROOT.parent)} "
        f"скриптом api/scripts/extract_homework.py. Не редактировать вручную."
        f"{' ' + note if note else ''} -->\n\n"
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"Не найден каталог с материалами: {SOURCE}")
        return 1

    written = 0
    problems = []
    for task in TASKS:
        folder = TARGET / task.slug
        (folder / "solutions").mkdir(parents=True, exist_ok=True)

        statement_source = SOURCE / task.statement_path
        try:
            statement = strip_criteria(read(statement_source))
        except Exception as error:  # noqa: BLE001
            problems.append(f"{task.slug}: условие — {error}")
            continue
        if len(statement) < 200:
            problems.append(f"{task.slug}: условие подозрительно короткое ({len(statement)} симв.)")
        (folder / "statement.md").write_text(
            header(statement_source, "Раздел «Критерии оценивания» вырезан: шкала живёт в рубрике.")
            + statement + "\n",
            encoding="utf-8",
        )
        written += 1

        for solution in task.solutions:
            source = SOURCE / solution.path
            try:
                text = read(source)
            except Exception as error:  # noqa: BLE001
                problems.append(f"{task.slug}/{solution.level}: {error}")
                continue
            if len(text) < 200:
                problems.append(
                    f"{task.slug}/{solution.level}: пусто или почти пусто ({len(text)} симв.) — {solution.path}"
                )
                continue
            (folder / "solutions" / f"{solution.level}-{Path(solution.path).stem}.md").write_text(
                header(source) + text + "\n", encoding="utf-8"
            )
            written += 1

    print(f"Записано файлов: {written} в {TARGET.relative_to(ROOT.parent)}")
    for line in problems:
        print("  ⚠", line)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
