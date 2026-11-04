"""What the compute paths [D1]/[D2] return, the confidence signals [V] collects, and the decision [E] takes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from .answer import AnswerType

Coverage = Literal["full", "partial", "none"]


class ExecResult(BaseModel):
    value: Any  # already in the answer type's shape (number, list, table dict…), before §9 rounding
    answer_type: AnswerType
    source: Literal["D1", "D2"]
    function: str | None = None  # metric function or generated-code id
    rule_ids: list[str] = []  # rulebook rows the computation relies on (checked by [R])
    requires: list[str] = []  # canonical "table.column" the computation needs
    notes: list[str] = []


class Signals(BaseModel):
    """Evidence for the decision. Defaults are the pessimistic value, so a block that did not run cannot help."""
    intent_known: bool = False
    out_of_scope: bool = False
    mapping_ok: bool = False
    entities_ok: bool = False
    required_fields_present: bool | None = None  # None: unknown
    period_coverage: Coverage | None = None
    compare_coverage: Coverage | None = None
    sane: bool = False
    rules_unchanged: bool = False
    paths_agree: bool | None = None  # D1 vs D2, when both ran
    twin_ok: bool | None = None  # T4: an LLM plan has a verified twin or the baseline's agreement; None = not gated
    notes: list[str] = []


class Decision(BaseModel):
    kind: Literal["answer", "unanswerable", "abstain"]
    confidence: float = 0.0
    reason: str = ""
