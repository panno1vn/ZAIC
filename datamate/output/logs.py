"""One JSON log file per question in <out>/logs/: id, answer, elapsed time and every intermediate result. BTC uses
these logs to explain differences between the uploaded result and their re-run."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    return obj


def write_log(log_dir: Path, name: str, record: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{_SAFE.sub('_', name)}.json"
    data = {k: to_jsonable(v) for k, v in record.items()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path
