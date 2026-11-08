"""One JSON log record per question in <out>/logs/: id, answer, elapsed time and every intermediate result. BTC uses
these logs to explain differences between the uploaded result and their re-run.

Docker guideline 2026 §3.3: one record per question, on one line, with id, answer, elapsed_ms, thinking (null when no
reasoning was generated) and, for a question solved by code, code (the source file and function), its actual inputs
and output. Each question gets its own file <id>.json (one line) and a line in questions.jsonl."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
QUESTIONS_JSONL = "questions.jsonl"


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    return obj


def _line(record: dict) -> str:
    return json.dumps({k: to_jsonable(v) for k, v in record.items()}, ensure_ascii=False, default=str)


def write_log(log_dir: Path, name: str, record: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{_SAFE.sub('_', name)}.json"
    path.write_text(_line(record) + "\n", encoding="utf-8")
    return path


def append_log(log_dir: Path, record: dict) -> None:
    """The question's record as one line of <log_dir>/questions.jsonl (guideline §3.3)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / QUESTIONS_JSONL, "a", encoding="utf-8") as fh:
        fh.write(_line(record) + "\n")
