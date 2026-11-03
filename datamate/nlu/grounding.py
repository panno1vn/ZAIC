"""Every filter of a plan must be grounded in the question. With "filters" required in the generation schema the LLM
stopped dropping filters but began inventing them (K3 run 2, 05/11: 10/123 plans with a filter the question never
names). A filter is grounded when its words are in the question (folded, small typos allowed), or, for a coded field,
when the question has one of its trigger words; a plan with an ungrounded filter is not used.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from datamate.contracts import QueryPlan

from .baseline import fold

TRIGGERS = {  # coded fields: words (folded) that must appear for the filter to be asked for
    "shift": ("ca", "sang", "chieu", "toi"),
    "weekday": ("thu", "chu nhat", "cuoi tuan", "ngay le"),
    "order_status": ("huy", "tra", "giao", "hoan thanh", "thanh cong", "doi y"),
    "prescription": ("ke don", "theo don", "toa"),
    "is_warranty": ("bao hanh",),
    "size": ("size", "co", "m", "l", "s"),
}
NUMERIC = {"order_value", "debt_age_days", "expiry_within_days"}


def _grounded_text(value: str, question_tokens: list[str], question: str) -> bool:
    words = fold(value).split()
    if not words:
        return False
    if " ".join(words) in question:
        return True
    hits = sum(any(fuzz.ratio(w, q) >= 80 for q in question_tokens) for w in words)
    return hits / len(words) >= 0.6


def ungrounded_filters(question: str, plan: QueryPlan) -> list[str]:
    """The filters of `plan` the question gives no ground for, as "field=value"."""
    q = fold(question)
    tokens = q.split()
    measures = list(plan.measures) + ([plan.share_of] if plan.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((plan.compare.filters or []) if plan.compare else [])
    bad = []
    for f in filters:
        values = f.value if isinstance(f.value, list) else [f.value]
        if f.field in TRIGGERS:
            ok = any(re.search(rf"\b{re.escape(t)}\b", q) for t in TRIGGERS[f.field])
        elif f.field in NUMERIC:
            ok = all(str(int(v)) in re.sub(r"[.,]", "", question) for v in values if isinstance(v, (int, float)))
        else:
            ok = all(_grounded_text(str(v), tokens, q) for v in values)
        if not ok:
            bad.append(f"{f.field}={f.value}")
    return bad
