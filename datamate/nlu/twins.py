"""Twin questions (T4). The train questions are generated from templates (docs/research/templates.md), so a new
question nearly always has a verified twin: a train question of another business with the same template text whose
plan ran to the right answer. A plan of the same shape as such a twin's is trusted; a plan of another shape is a
reading the train set never confirmed.

The bank (assets/plans/verified_train.jsonl, eval/build_bank.py) stores each question's template text, masked with
the names of its own business at build time; a new question is masked with the names of its business's canonical
data.
"""
from __future__ import annotations

import json
import re
import weakref
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from datamate.contracts import CanonicalDB, QueryPlan

from .templates import NameIndex, plan_shape, template_text

BANK = Path(__file__).resolve().parents[2] / "assets" / "plans" / "verified_train.jsonl"

# canonical columns holding names, and the role tag each gets in a template text (the roles of NameIndex)
NAME_COLUMNS = [("lines", "product_name", "sp"), ("products", "product_name", "sp"), ("products", "product_group", "nhom"),
                ("lines", "product_group", "nhom"), ("products", "active_ingredient", "hc"),
                ("customers", "customer_name", "kh"), ("orders", "customer_name", "kh"),
                ("employees", "employee_name", "nv"), ("purchases", "supplier", "ncc"),
                ("orders", "customer_group", "nhomkh")]


def names_from_db(db: CanonicalDB) -> NameIndex:
    """The names a business's data holds, for masking its questions."""
    out = set()
    for table, col, role in NAME_COLUMNS:
        df = db.table(table)
        if df is not None and col in df.columns:
            out |= {(role, str(v)) for v in df[col].dropna().unique() if str(v).strip()}
    return NameIndex(sorted(out))


# Period kinds of one family share a twin: run 04/11 (790 questions, examples of other businesses only) the gate
# lost 11 right answers, most for a period kind no verified twin had ("tháng này" where the bank had "tháng 3"), and
# of 61 template readings that differed only so, none was a misreading. Kinds that change what is asked stay apart:
# "until" (stock), "quarter" vs "month", "tet", ranges.
PERIOD_FAMILY = {"today": "day", "yesterday": "day", "this_week": "week", "last_week": "week",
                 "this_month": "month", "last_month": "month"}


def twin_shape(plan: QueryPlan) -> str:
    """plan_shape with the period kind replaced by its family."""
    shape = plan_shape(plan)
    for p in filter(None, (plan.period, plan.compare.period if plan.compare else None)):
        if p.kind in PERIOD_FAMILY:
            shape = re.sub(rf"\b{p.kind}\b", PERIOD_FAMILY[p.kind], shape)
    return shape


@dataclass(frozen=True)
class Twin:
    score: float  # similarity of the template texts, 0–100; 0 when no verified question has the plan's shape
    question_id: str | None = None

    def passes(self, threshold: float) -> bool:
        """A twin exists and is similar enough; with no twin even threshold 0 fails."""
        return self.question_id is not None and self.score >= threshold


class TwinIndex:
    """Verified questions grouped by plan shape, each with its template text."""

    def __init__(self, items: list[dict]):
        self.by_shape: dict[str, list[dict]] = defaultdict(list)
        for e in items:
            self.by_shape[e["shape"]].append(e)

    @classmethod
    def from_file(cls, path: Path = BANK) -> "TwinIndex":
        items = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    items.append({"id": e["id"], "business_id": e["business_id"], "text": e["text"],
                                  "shape": twin_shape(QueryPlan.model_validate(e["plan"]))})
        return cls(items)

    def __len__(self) -> int:
        return sum(len(v) for v in self.by_shape.values())

    def twin(self, text: str, plan: QueryPlan, exclude_business: str | None = None,
             exclude_ids: frozenset[str] = frozenset()) -> Twin:
        """The most similar verified question whose plan has the shape of `plan`; leaving out a business or some
        questions gives the leave-one-business-out measure on train."""
        pool = [e for e in self.by_shape.get(twin_shape(plan), [])
                if e["business_id"] != exclude_business and e["id"] not in exclude_ids]
        if not pool:
            return Twin(0.0)
        hit = process.extractOne(text, [e["text"] for e in pool], scorer=fuzz.token_sort_ratio)
        return Twin(float(hit[1]), pool[hit[2]]["id"])


@lru_cache(maxsize=1)
def default_index() -> TwinIndex:
    return TwinIndex.from_file()


_NAMES: dict[int, tuple[weakref.ref, NameIndex]] = {}


def question_text(question: str, db: CanonicalDB) -> str:
    """Template text of a question, masked with its business's names (built once per business)."""
    ref, names = _NAMES.get(id(db), (None, None))
    if ref is None or ref() is not db:
        names = names_from_db(db)
        _NAMES[id(db)] = (weakref.ref(db), names)
    return template_text(question, names)
