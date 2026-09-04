"""Minimal, bounded adapter for public GitHub homework repositories."""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from ..config import settings


MAX_ARCHIVE_BYTES = 12 * 1024 * 1024
MAX_FILE_BYTES = 350 * 1024
SECTION_SEPARATOR = "\n\n---\n\n"
TRUNCATION_NOTE = "\n[Файл обрезан по лимиту снапшота]"
ALLOWED_SUFFIXES = {".py", ".ipynb", ".md", ".txt", ".yaml", ".yml", ".toml", ".json"}
IGNORED_PARTS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}


class GithubSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class GithubSnapshot:
    content: str
    content_hash: str
    parsed_facts: dict


def _repository(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise GithubSnapshotError("Поддерживаются только HTTPS-ссылки на GitHub")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise GithubSnapshotError("Ссылка должна указывать на GitHub-репозиторий")
    owner, repository = parts[:2]
    repository = repository.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", repository
    ):
        raise GithubSnapshotError("Некорректная ссылка на GitHub-репозиторий")
    return owner, repository


def _notebook_text(path: str, raw: bytes) -> tuple[str, list[int], int]:
    try:
        notebook = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GithubSnapshotError(f"Не удалось прочитать notebook {path}") from exc
    chunks = [f"# Файл: {path}"]
    execution_counts: list[int] = []
    failed_cells = 0
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        cell_type = cell.get("cell_type", "unknown")
        execution_count = cell.get("execution_count")
        if isinstance(execution_count, int):
            execution_counts.append(execution_count)
        chunks.append(
            f"\n## Ячейка {index} · {cell_type}"
            + (f" · execution_count={execution_count}" if execution_count is not None else "")
        )
        source = cell.get("source", "")
        chunks.append("".join(source) if isinstance(source, list) else str(source))
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                failed_cells += 1
                chunks.append(
                    f"[Ошибка: {output.get('ename', '')}: {output.get('evalue', '')}]"
                )
    return "\n".join(chunks), execution_counts, failed_cells


def build_snapshot(archive: bytes, max_chars: int | None = None) -> GithubSnapshot:
    """Собирает снапшот в пределах `max_chars`.

    Отброшенное лимитом попадает в `parsed_facts` (`truncated`, `omitted_files`):
    «модель не увидела файл» должно читаться из снапшота, а не выясняться перебором.
    """

    limit = settings.max_snapshot_chars if max_chars is None else max_chars
    sections: list[str] = []
    used = 0
    execution_counts: list[int] = []
    failed_cells = 0
    included_files: list[str] = []
    omitted_files: list[str] = []
    truncated = False
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise GithubSnapshotError("GitHub вернул повреждённый архив") from exc

    for info in sorted(bundle.infolist(), key=lambda item: item.filename):
        path = PurePosixPath(info.filename)
        if info.is_dir() or info.file_size > MAX_FILE_BYTES:
            continue
        relative_parts = path.parts[1:]
        if not relative_parts or any(part in IGNORED_PARTS or part.startswith(".") for part in relative_parts):
            continue
        relative = str(PurePosixPath(*relative_parts))
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        if truncated:
            omitted_files.append(relative)
            continue
        raw = bundle.read(info)
        if path.suffix.lower() == ".ipynb":
            text, counts, errors = _notebook_text(relative, raw)
        else:
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            text, counts, errors = f"# Файл: {relative}\n\n{decoded}", [], 0
        # used считает длину итогового content вместе с разделителями, поэтому
        # snapshot_chars в фактах никогда не превысит snapshot_limit.
        separator = len(SECTION_SEPARATOR) if sections else 0
        if used + separator + len(text) > limit:
            truncated = True
            remaining = limit - used - separator - len(TRUNCATION_NOTE)
            if remaining > 500:
                text = text[:remaining] + TRUNCATION_NOTE
            else:
                omitted_files.append(relative)
                continue
        sections.append(text)
        used += separator + len(text)
        included_files.append(relative)
        execution_counts.extend(counts)
        failed_cells += errors

    if not sections:
        raise GithubSnapshotError("В репозитории нет поддерживаемых текстовых файлов")
    content = SECTION_SEPARATOR.join(sections)
    lowered = content.lower()
    run_markers = len(re.findall(r"mlflow\.start_run\s*\(", lowered))
    metrics = sorted(
        set(re.findall(r"['\"](accuracy|precision|recall|f1|roc_auc|mae|mse|rmse)['\"]", lowered))
    )
    facts = {
        "files": included_files,
        "notebook_execution_counts": execution_counts,
        "runs_in_code": run_markers,
        "metrics": metrics,
        "seed_fixed": bool(re.search(r"(random_state|seed)\s*=\s*\d+", lowered)),
        "registered_model": bool(
            re.search(r"register_model|registered_model_name|create_registered_model", lowered)
        ),
        "failed_cells": failed_cells,
        "snapshot_chars": len(content),
        "snapshot_limit": limit,
        "truncated": truncated,
        "omitted_files": omitted_files,
    }
    return GithubSnapshot(
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        parsed_facts=facts,
    )


def fetch_github_snapshot(url: str) -> GithubSnapshot:
    owner, repository = _repository(url)
    archive_url = f"https://codeload.github.com/{owner}/{repository}/zip/HEAD"
    request = urllib.request.Request(
        archive_url,
        headers={"User-Agent": "Avito-AI-Reviewer/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            archive = response.read(MAX_ARCHIVE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GithubSnapshotError("Репозиторий не найден или не является публичным") from exc
        raise GithubSnapshotError(f"GitHub вернул ошибку {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GithubSnapshotError("Не удалось загрузить репозиторий с GitHub") from exc
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise GithubSnapshotError("Архив репозитория превышает лимит 12 МБ")
    return build_snapshot(archive)
