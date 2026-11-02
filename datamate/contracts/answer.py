"""Answer types and the submission line format (rulebook §9). Shared by the formatter [F] and the local scorer."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, model_validator

AnswerType = Literal["number", "percent", "date", "boolean", "string", "list", "table"]
LineType = Literal["number", "percent", "date", "boolean", "string", "list", "table", "unanswerable", "abstain"]
VALUE_TYPES: tuple[str, ...] = ("number", "percent", "date", "boolean", "string", "list", "table")
ALL_TYPES: tuple[str, ...] = VALUE_TYPES + ("unanswerable", "abstain")
_DATE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def valid_date(s: Any) -> bool:
    """'YYYY-MM-DD', or 'YYYY-MM' for questions asked by month."""
    if not isinstance(s, str):
        return False
    m = _DATE.match(s)
    if not m:
        return False
    try:
        date(int(m[1]), int(m[2]), int(m[3] or 1))
    except ValueError:
        return False
    return True


def format_error(line: dict) -> str | None:
    """None when the line has the single valid format of its type, else the reason (a malformed line is wrong)."""
    t = line.get("type")
    if t not in ALL_TYPES:
        return f"type không hợp lệ: {t!r}"
    if t in ("abstain", "unanswerable"):
        return None
    if "answer" not in line:
        return "thiếu trường answer"
    a = line["answer"]
    if t in ("number", "percent"):
        ok = is_number(a)
    elif t == "date":
        ok = valid_date(a)
    elif t == "boolean":
        ok = isinstance(a, bool)
    elif t == "string":
        ok = isinstance(a, str)
    elif t == "list":
        ok = isinstance(a, list)
    else:  # table
        cols = a.get("columns") if isinstance(a, dict) else None
        rows = a.get("rows") if isinstance(a, dict) else None
        ok = (isinstance(cols, list) and all(isinstance(c, str) for c in cols) and isinstance(rows, list)
              and all(isinstance(r, list) and len(r) == len(cols) for r in rows))
    return None if ok else f"answer sai format của type {t}"


class SubmissionLine(BaseModel):
    """One line of submission.jsonl. Construction fails if the answer does not have its type's format."""
    id: str
    type: LineType
    answer: Any = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_format(self) -> "SubmissionLine":
        err = format_error(self.to_dict())
        if err:
            raise ValueError(err)
        return self

    def to_dict(self) -> dict:
        out: dict = {"id": self.id, "type": self.type}
        if self.type in VALUE_TYPES:
            out["answer"] = self.answer
        if self.type == "unanswerable" and self.reason:
            out["reason"] = self.reason
        return out

    @classmethod
    def abstain(cls, qid: str) -> "SubmissionLine":
        return cls(id=qid, type="abstain")
