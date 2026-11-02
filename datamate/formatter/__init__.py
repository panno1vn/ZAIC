"""[F] Write the final answer in the single format of its type (rulebook §9). Work package G4.

Rounding (§9 "Làm tròn"): money to whole đồng, half up; percents and other averages to 2 decimals, half up.
Metric functions round money themselves with `money()`; the formatter enforces the format and 2-decimal rounding.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from datamate.contracts import Decision, ExecResult, SubmissionLine


def round_half_up(x: float, digits: int = 0) -> Decimal:
    return Decimal(str(x)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def money(x: float) -> int:
    """Amount in whole đồng, half up (Python's round() rounds half to even, which §9 does not)."""
    return int(round_half_up(x, 0))


def _number(v: Any) -> Any:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    d = round_half_up(v, 2)
    return int(d) if d == d.to_integral_value() else float(d)


def format_value(answer_type: str, v: Any) -> Any:
    if answer_type == "number":
        return _number(v)
    if answer_type == "percent":
        return float(round_half_up(v, 2))
    if answer_type in ("date", "string"):
        return str(v)
    if answer_type == "list":
        return [_number(x) for x in v]
    if answer_type == "table":
        return {"columns": [str(c) for c in v["columns"]], "rows": [[_number(c) for c in row] for row in v["rows"]]}
    return v


def to_line(qid: str, decision: Decision, result: ExecResult | None) -> SubmissionLine:
    if decision.kind == "unanswerable":
        return SubmissionLine(id=qid, type="unanswerable", reason=decision.reason or None)
    if decision.kind == "answer" and result is not None:
        try:
            return SubmissionLine(id=qid, type=result.answer_type, answer=format_value(result.answer_type, result.value))
        except Exception:  # a value that does not fit its type's format is not worth −1
            return SubmissionLine.abstain(qid)
    return SubmissionLine.abstain(qid)
