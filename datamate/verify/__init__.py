"""[V] Check a result and collect the signals the decision [E] uses. Leader.

Every signal starts pessimistic (contracts.results.Signals) and is raised only on evidence.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

from datamate.contracts import CanonicalDB, ExecResult, Filter, Mapping, ResolvedPeriod, ResolvedPlan, Signals

# filter fields whose value must be found in the data by [C3]; others (shift, weekday, size, numbers) need no linking
LINKED_FIELDS = frozenset({
    "product", "product_group", "category", "product_line", "brand", "active_ingredient", "customer",
    "customer_group", "channel", "payment_method", "employee", "supplier", "service", "vehicle_model", "plate",
})


def filter_keys(f: Filter) -> list[str]:
    """Keys under which [C3] records the linked value of a filter: each value as written."""
    values = f.value if isinstance(f.value, list) else [f.value]
    return [str(v) for v in values]


def coverage(period: ResolvedPeriod | None, span: tuple[date, date] | None) -> str | None:
    """How much of the period lies inside the data's date span: full / partial / none (§7)."""
    if period is None:
        return "full"
    if span is None:
        return None
    lo, hi = span
    if period.mode == "stock":
        return "none" if period.end < lo else "full"
    if period.end < lo or period.start > hi:
        return "none"
    return "full" if period.start >= lo and period.end <= hi else "partial"


# §7 rows the "period wholly outside the shop's data: unanswerable" decision relies on (N28)
R_OUTSIDE = ("§7.p_cau_khong_tra_loi_duoc_khi", "§7.p_khong_co_du_lieu_khac_voi")


# tables without their own dates take the span of the table that dates them
DATE_OWNER = {"lines": "orders", "lot_sales": "orders", "payments": "orders", "returns": "orders",
              "deliveries": "orders", "installments": "orders"}


def data_span(db: CanonicalDB, requires: list[str]) -> tuple[date, date] | None:
    """Date span of the data a result relies on: first required table with a span, else its dating table."""
    for table in [r.split(".")[0] for r in requires] + ["orders"]:
        for t in (table, DATE_OWNER.get(table)):
            if t and t in db.date_ranges:
                return db.date_ranges[t]
    return None


def _sane(result: ExecResult) -> bool:
    v = result.value
    if v is None:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return math.isfinite(v)
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        return bool(v.get("rows"))
    return True


# N37: a time in the question ("tháng 12/2025", "hôm qua", "Tết"): an out-of-scope reading of it is an LLM misreading
# of a figure, not a question the data cannot hold (train 05/11: 7 of 8 out-of-scope readings have no time, all
# unanswerable; the eighth, "nhân viên bán giỏi nhất tháng 12/2025", is a ranking)
_TIME = re.compile(r"\b(?:thang|tuan|quy|ngay|hom nay|hom qua|bua qua|bua nay|hqua|tet|nam nay|nam ngoai|nam truoc"
                   r"|nam \d{4}|\d{1,2}/\d{2,4}|\d{4})\b")


# N38, train 05/11: the 104 purchase questions of shops whose README conventions name "Nhập hàng" are answerable, the
# 5 of the shops whose conventions do not are all unanswerable
PURCHASE_METRICS = frozenset({"purchase_amount", "purchase_avg_cost", "receipt_count", "purchase_minus_sales"})


def _asks_purchases(p) -> bool:
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    return any(m.metric in PURCHASE_METRICS for m in measures) or (p.rank is not None and p.rank.entity == "supplier")


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def collect_signals(plan: ResolvedPlan | None, result: ExecResult | None, db: CanonicalDB, mapping: Mapping,
                    rules: dict[str, bool], question: str = "") -> Signals:
    s = Signals(mapping_ok=mapping.ok)
    if plan is None:
        return s
    p = plan.plan
    s.intent_known = True
    s.out_of_scope = p.intent == "out_of_scope"
    if s.out_of_scope and question and all(rules.get(r, False) for r in R_OUTSIDE):
        s.subjective = not _TIME.search(_fold(question))
    measures = list(p.measures) + ([p.share_of] if p.share_of else [])
    filters = [f for m in measures for f in m.filters] + list((p.compare.filters or []) if p.compare else [])
    linkable = [k for f in filters if f.field in LINKED_FIELDS for k in filter_keys(f)]
    s.entities_ok = all(k in plan.linked for k in linkable)  # no linkable filter: nothing to link, so ok
    if plan.omitted:  # N36: a name the question writes is missing from the plan
        s.entities_ok = False
    if all(rules.get(r, False) for r in R_OUTSIDE) and _asks_purchases(p) and db.conventions is not None \
            and "nhap hang" not in db.conventions and not db.has("purchases"):
        s.not_recorded = True  # N38: the README's conventions name no purchases, and none were mapped (§7)
    shop = db.date_ranges.get("orders")  # §7 "khoảng ngày có dữ liệu của shop", not the span of one table
    if plan.period is not None and shop is not None and all(rules.get(r, False) for r in R_OUTSIDE):
        compared = plan.compare_period if p.compare is not None and p.compare.kind != "filter" else None
        s.outside_data = any(coverage(x, shop) == "none" for x in (plan.period, compared) if x is not None)
    if result is None:
        return s
    s.required_fields_present = all(
        db.has(*r.split(".", 1)) if "." in r else db.has(r) for r in result.requires)
    span = data_span(db, result.requires)
    s.period_coverage = coverage(plan.period, span)
    if p.compare is not None and p.compare.kind != "filter":
        s.compare_coverage = coverage(plan.compare_period, span)
    s.sane = _sane(result)
    if "tie" in result.notes:  # metrics.sales.TIE: the generator leaves ties out, so ours mean a misread (N25)
        s.ranking_clear = False
    s.rules_unchanged = bool(result.rule_ids) and all(rules.get(r, False) for r in result.rule_ids)
    return s
