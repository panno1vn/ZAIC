"""Local scorer for DataMate submissions, following rulebook §9 (đúng +1, sai −1, bỏ trống 0).

Where §9 leaves room for interpretation this scorer takes the strictest reading, so a local score should never be
higher than the official one:
- strings ignore case, whitespace and Unicode punctuation (category P*) only; diacritics and symbols such as "+" count;
- numbers and percents must match exactly up to floating-point noise;
- a line whose `reason` is not a string is unreadable and counts as blank (§7).
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datamate.contracts.answer import ALL_TYPES, VALUE_TYPES, format_error, is_number, valid_date  # noqa: F401

POINTS = {"correct": 1, "wrong": -1, "abstain": 0}


@dataclass(frozen=True)
class Verdict:
    id: str
    outcome: str  # "correct" | "wrong" | "abstain"
    reason: str = ""

    @property
    def points(self) -> int:
        return POINTS[self.outcome]


# ---------------------------------------------------------------- value helpers
def norm_text(s: str) -> str:
    """Case, whitespace and punctuation are ignored; Vietnamese diacritics are kept."""
    s = unicodedata.normalize("NFC", s).casefold()
    return "".join(c for c in s if not c.isspace() and not unicodedata.category(c).startswith("P"))


def same_number(a: Any, b: Any) -> bool:
    return is_number(a) and is_number(b) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


# ---------------------------------------------------------------- comparison
def _element_aliases(alias: Any, i: int) -> list:
    """Aliases of element i of a list or table answer (alias is a list of lists there)."""
    if isinstance(alias, list) and i < len(alias) and isinstance(alias[i], list):
        return alias[i]
    return []


def _match_name(pred: Any, ref: str, aliases: list) -> bool:
    if not isinstance(pred, str):
        return False
    target = norm_text(pred)
    return any(target == norm_text(c) for c in [ref, *aliases] if isinstance(c, str))


def _match_cell(pred: Any, ref: Any, aliases: list = ()) -> bool:
    if isinstance(ref, str):
        return _match_name(pred, ref, list(aliases))
    if isinstance(ref, bool):
        return pred is ref
    return same_number(pred, ref)


def _match_table(pred: dict, ref: dict, alias: Any) -> bool:
    """Columns by name, else by position; rows in any order; first column is the object's name."""
    rcols, pcols = ref["columns"], pred["columns"]
    if len(rcols) != len(pcols) or len(ref["rows"]) != len(pred["rows"]):
        return False
    by_name = {norm_text(c): i for i, c in enumerate(pcols)}
    if len(by_name) == len(pcols) and all(norm_text(c) in by_name for c in rcols):
        order = [by_name[norm_text(c)] for c in rcols]
    else:
        order = list(range(len(rcols)))
    rows = [[row[k] for k in order] for row in pred["rows"]]
    used = [False] * len(rows)
    for j, rrow in enumerate(ref["rows"]):
        names = _element_aliases(alias, j)
        for k, prow in enumerate(rows):
            if (not used[k] and _match_cell(prow[0], rrow[0], names)
                    and all(_match_cell(p, r) for p, r in zip(prow[1:], rrow[1:]))):
                used[k] = True
                break
        else:
            return False
    return True


def compare_value(t: str, pred: Any, ref: Any, alias: Any) -> bool:
    if t in ("number", "percent"):
        return same_number(pred, ref)
    if t == "date":
        return pred == ref
    if t == "boolean":
        return pred is ref
    if t == "string":
        names = alias if isinstance(alias, list) and all(isinstance(x, str) for x in alias) else []
        return _match_name(pred, ref, names)
    if t == "list":
        return len(pred) == len(ref) and all(
            _match_cell(p, r, _element_aliases(alias, i)) for i, (p, r) in enumerate(zip(pred, ref)))
    if t == "table":
        return _match_table(pred, ref, alias)
    return False


def score_line(pred: dict | None, ref: dict) -> Verdict:
    """Score one submission line against its reference line from answers.jsonl."""
    qid = ref["id"]
    if pred is None:
        return Verdict(qid, "abstain", "không có dòng")
    if "reason" in pred and not isinstance(pred["reason"], str):
        return Verdict(qid, "abstain", "reason không phải chuỗi: tính như bỏ trống")
    t = pred.get("type")
    if t == "abstain":
        return Verdict(qid, "abstain", "abstain")
    err = format_error(pred)
    if err:
        return Verdict(qid, "wrong", err)
    if t != ref["type"]:
        return Verdict(qid, "wrong", f"type {t} khác đáp án {ref['type']}")
    if t == "unanswerable":
        return Verdict(qid, "correct")
    if compare_value(t, pred["answer"], ref["answer"], ref.get("alias")):
        return Verdict(qid, "correct")
    return Verdict(qid, "wrong", "giá trị khác đáp án")


# ---------------------------------------------------------------- files
def read_jsonl(path: str | Path) -> tuple[list[dict], list[str]]:
    """Parsed JSON objects of a JSON Lines file, plus one warning per unreadable line."""
    rows, warnings = [], []
    with open(path, encoding="utf-8-sig") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                warnings.append(f"dòng {n}: JSON lỗi ({e.msg})")
                continue
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
                warnings.append(f"dòng {n}: không phải object có id")
                continue
            rows.append(obj)
    return rows, warnings


def index_submission(lines: list[dict], ref_ids: set[str]) -> tuple[dict[str, dict], list[str]]:
    """Submission lines keyed by id (a later duplicate replaces an earlier one), plus warnings."""
    by_id, warnings = {}, []
    for obj in lines:
        qid = obj["id"]
        if qid in by_id:
            warnings.append(f"id {qid} lặp lại: lấy dòng sau")
        by_id[qid] = obj
    extra = sorted(set(by_id) - ref_ids)
    if extra:
        warnings.append(f"{len(extra)} id không có trong đáp án, bỏ qua (ví dụ {extra[0]})")
    return by_id, warnings


def score_submission(pred_lines: list[dict], refs: list[dict]) -> tuple[list[Verdict], list[str]]:
    by_id, warnings = index_submission(pred_lines, {r["id"] for r in refs})
    return [score_line(by_id.get(r["id"]), r) for r in refs], warnings


def penalized_accuracy(verdicts: list[Verdict]) -> float:
    return sum(v.points for v in verdicts) / len(verdicts) if verdicts else 0.0
