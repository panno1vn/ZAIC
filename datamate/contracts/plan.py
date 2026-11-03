"""Query plan: what a question asks for, as produced by [C] (LLM, structured output) and resolved by [C2].

The LLM only extracts. Periods stay symbolic here ("this_month", "month 2025-06") and are turned into dates by the
temporal engine [C2]; names stay as written in the question (`Filter.value`) and are linked to data by [C3].
`answer_type` may be left out: it follows from the plan's shape (`expected_answer_type`).
v1.1 (K2, contract stress test on 99 train questions): coded filter values, list counts, count_where without
measures, expiry windows as periods, Tết without a year, STOCK_METRICS.
Design notes and question counts: docs/research/intents.md, docs/research/periods.md; rulebook coverage:
docs/contracts.md.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .answer import AnswerType
from .canonical import ORDER_STATUSES


class _Model(BaseModel):
    """Unknown fields are errors: a misspelt "filter" for "filters" must reject the plan, not drop the filter."""
    model_config = ConfigDict(extra="forbid")

Metric = Literal[
    # bán hàng (§1, §3)
    "revenue", "order_count", "cancel_count", "cancel_rate", "avg_order_value", "quantity",
    "customer_count", "new_customer_count", "days_with_purchase", "order_presence", "work_days",
    # nhập hàng, kho, giá vốn (§5, nhà thuốc)
    "purchase_amount", "purchase_avg_cost", "receipt_count", "purchase_minus_sales",
    "stock_qty", "stock_value", "nearest_expiry", "expiring_value",
    # công nợ, thanh toán (§1, §4, điện thoại)
    "debt_total", "debtor_count", "debt_amount", "debt_added", "debt_paid", "cash_collected",
    "amount_due_total", "overdue_installment_count", "overdue_amount",
    # giá, lãi (§5)
    "unit_price", "gross_profit", "net_profit",
    # theo ngành (§6): vật liệu xây dựng, mẹ và bé, sửa xe, điện thoại
    "delivery_count", "voucher_discount", "points_discount", "shipping_fee_total",
    "ticket_count", "avg_ticket_value", "vehicle_count", "warranty_count", "warranty_rate", "trade_in_amount",
    "other",
]
PERCENT_METRICS = frozenset({"cancel_rate", "warranty_rate"})
DATE_METRICS = frozenset({"nearest_expiry"})
# measured as the state at the end of a day (§2 "Đến hết ngày X"): [C2] resolves their period in mode stock, from the
# start of the data, whatever kind the plan has ("tồn cuối ngày hôm nay" may come as kind today)
STOCK_METRICS = frozenset({"debt_total", "debtor_count", "debt_amount", "stock_qty", "stock_value", "nearest_expiry",
                           "expiring_value", "overdue_installment_count", "overdue_amount"})

FilterField = Literal[
    "product", "product_group", "category", "product_line", "brand", "size", "stage", "unit",
    "active_ingredient", "prescription", "customer", "customer_group", "channel", "payment_method",
    "employee", "supplier", "shift", "weekday", "order_status", "order_value", "debt_age_days",
    "expiry_within_days", "service", "vehicle_model", "plate", "is_warranty", "other",
]
FilterOp = Literal["eq", "ne", "in", "not_in", "gte", "gt", "lte", "lt", "contains"]
# filter fields whose value is a code, not a name for [C3] to link: the plan writes the code, so [D1] never has to
# guess a spelling ("ca sáng", "sang", "buổi sáng")
CODED_VALUES: dict[str, tuple] = {
    "shift": ("morning", "afternoon"),  # ca sáng 06:00–13:59, ca chiều 14:00–21:59 (§2)
    "weekday": ("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
    "order_status": ORDER_STATUSES,
    "prescription": (True, False),
    "is_warranty": (True, False),
}
PeriodKind = Literal[
    "day", "today", "yesterday", "this_week", "last_week", "this_month", "last_month", "month", "quarter", "year",
    "ytd", "last_n_days", "next_n_days", "range", "months", "until", "days_from", "tet", "all",
]
CompareKind = Literal[
    "previous", "previous_same_days", "same_period_last_year", "before_tet", "before_days_from", "period", "filter",
]
Intent = Literal["value", "compare", "share", "rank", "count_where", "trend", "series", "list_items", "out_of_scope"]
RankEntity = Literal[
    "product", "product_group", "product_line", "brand", "customer", "employee", "supplier", "vehicle",
    "day", "month", "hour", "weekday", "lot",
]
ListCondition = Literal[
    "unsold_in_period", "out_of_stock_end_of_day", "expiring_within", "in_stock", "sold_in_period", "debtor",
    "overdue_installment", "returning_vehicle",
]

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")


class Filter(_Model):
    field: FilterField
    op: FilterOp = "eq"
    # names as written in the question ([C3] links them to the data); codes of CODED_VALUES; numbers for bounds
    value: bool | str | float | list[str] | list[float] = Field(description=(
        "Tên như viết trong câu hỏi. Riêng các trường sau ghi mã: " + "; ".join(
            f"{k}: {', '.join(str(v).lower() for v in vs)}" for k, vs in CODED_VALUES.items())))
    note: str | None = None  # for field "other": what the filter means

    @model_validator(mode="after")
    def _coded_value(self) -> "Filter":
        allowed = CODED_VALUES.get(self.field)
        values = self.value if isinstance(self.value, list) else [self.value]
        if allowed is None:
            if any(isinstance(v, bool) for v in values):
                raise ValueError(f"filter {self.field} không nhận true/false")
        elif not all(type(v) is type(allowed[0]) and v in allowed for v in values):
            raise ValueError(f"filter {self.field} chỉ nhận {list(allowed)}, nhận {self.value!r}")
        return self


class Measure(_Model):
    metric: Metric
    filters: list[Filter] = []
    unit: str | None = None  # unit the question counts in: "ly", "chai", "kg"…
    aggregate: Literal["total", "avg_per_day", "avg_per_weekday"] = "total"  # §2 "trung bình mỗi ngày thứ X"
    unit_split: bool = False  # answer as [đơn vị lớn nguyên, đơn vị cơ bản lẻ] (tồn theo đơn vị lớn)
    note: str | None = None  # for metric "other": what is measured


class PeriodExpr(_Model):
    """Symbolic period. Which fields are needed depends on `kind` (checked below)."""
    kind: PeriodKind
    year: int | None = Field(None, ge=2000, le=2100)  # month / quarter / year; None = not stated (rulebook §2)
    month: int | None = Field(None, ge=1, le=12)
    quarter: int | None = Field(None, ge=1, le=4)
    date: str | None = None  # YYYY-MM-DD for day / until / days_from
    anchor_price: float | None = None  # days_from without a date: the day the price rose to this value (§5)
    start: str | None = None  # range: YYYY-MM-DD or YYYY-MM
    end: str | None = None  # range end, or last month of a "months" series (YYYY-MM)
    n: int | None = Field(None, ge=1)  # last_n_days, next_n_days, days_from, months (series length)
    months: list[str] | None = None  # explicit series, YYYY-MM each
    lunar_year: int | None = Field(None, ge=2000, le=2100)  # tet; None = "Tết năm nay" (lunar year of today, [C2])

    @model_validator(mode="after")
    def _fields_for_kind(self) -> "PeriodExpr":
        k = self.kind
        need = {"day": ["date"], "until": ["date"], "days_from": ["n"], "month": ["month"], "quarter": ["quarter"],
                "year": ["year"], "last_n_days": ["n"], "next_n_days": ["n"], "range": ["start", "end"]}.get(k, [])
        missing = [f for f in need if getattr(self, f) is None]
        if k == "days_from" and self.date is None and self.anchor_price is None:
            missing.append("date hoặc anchor_price")
        if k == "months" and not (self.months or (self.end and self.n)):
            missing.append("months hoặc end + n")
        if missing:
            raise ValueError(f"period {k} thiếu {missing}")
        bad = []
        if self.date is not None and not _valid_day(self.date):
            bad.append(f"date={self.date!r} (cần YYYY-MM-DD)")
        for name in ("start", "end"):
            v = getattr(self, name)
            if v is not None and not (_valid_day(v) or _MONTH.match(v)):
                bad.append(f"{name}={v!r} (cần YYYY-MM-DD hoặc YYYY-MM)")
        if k == "months" and self.end is not None and not _MONTH.match(self.end):
            bad.append(f"end={self.end!r} (chuỗi tháng cần YYYY-MM)")
        bad += [f"months[]={m!r} (cần YYYY-MM)" for m in self.months or [] if not _MONTH.match(m)]
        if bad:
            raise ValueError("sai định dạng: " + "; ".join(bad))
        return self


def _valid_day(s: str) -> bool:
    if not _DAY.match(s):
        return False
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return True


class Compare(_Model):
    """What the asked figure is compared with: another period, or the same period under other filters."""
    kind: CompareKind
    period: PeriodExpr | None = None  # kind "period": the explicit other period
    filters: list[Filter] | None = None  # kind "filter": filters of the base measure (e.g. ca sáng)
    output: Literal["pct_change", "diff", "which_more"] = "pct_change"
    n: int | None = None  # length stated in the question ("17 ngày trước Tết"), kept to cross-check the rule

    @model_validator(mode="after")
    def _payload(self) -> "Compare":
        if self.kind == "period" and self.period is None:
            raise ValueError("compare period cần trường period")
        if self.kind == "filter" and not self.filters:
            raise ValueError("compare filter cần trường filters")
        return self


class Rank(_Model):
    entity: RankEntity
    by: Metric  # the ranking criterion; measures[0].metric must agree when measures are given
    k: int | None = Field(1, ge=1)  # None = all (a "liệt kê" question)
    order: Literal["desc", "asc"] = "desc"
    min_orders: int | None = None  # e.g. "khách sộp": only customers with ≥ 3 orders
    with_values: bool = False  # answer is a table: name + measured value


class Threshold(_Model):
    """Count objects whose metric passes a bound: orders with revenue ≥ X, customers with ≥ N orders…
    The plan needs no measures; when given, measures[0] is this metric with its filters."""
    entity: Literal["order", "day", "product", "customer", "employee", "vehicle"]
    metric: Metric
    op: Literal["gte", "gt", "lte", "lt", "eq"]
    value: float
    as_share: bool = False  # "bao nhiêu % khách…": share of all objects of that entity instead of a count


class ListSpec(_Model):
    """Objects to list by a condition: hàng ế, hàng hết hàng cuối ngày, hàng hết hạn trong N ngày…"""
    entity: Literal["product", "customer", "lot", "vehicle", "order"]
    condition: ListCondition
    n: int | None = Field(None, ge=1)  # expiring_within: N days from today; or the plan's period is the expiry window
    count: bool = False  # "bao nhiêu mặt hàng ế": the answer is the number of objects, not the list


# each optional section belongs to one intent; a plan carrying another intent's section is rejected
SECTION_OWNER = {"compare": "compare", "rank": "rank", "threshold": "count_where", "list_spec": "list_items",
                 "share_of": "share"}


class QueryPlan(_Model):
    intent: Intent
    measures: list[Measure] = []  # in the order the question asks for them
    period: PeriodExpr | None = None  # None: state as of today, or the question needs no period
    compare: Compare | None = None
    rank: Rank | None = None
    threshold: Threshold | None = None
    list_spec: ListSpec | None = None
    share_of: Measure | None = None  # denominator of a share; None = same metric without filters
    answer_type: AnswerType | Literal["unanswerable"] | None = None  # None: derived from the plan's shape
    out_of_scope_reason: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "QueryPlan":
        i = self.intent
        if i == "out_of_scope" and not self.out_of_scope_reason:
            raise ValueError("out_of_scope cần out_of_scope_reason")
        if i not in ("out_of_scope", "rank", "list_items", "count_where") and not self.measures:
            raise ValueError(f"intent {i} cần ít nhất một measure")
        required = {"compare": "compare", "rank": "rank", "count_where": "threshold", "list_items": "list_spec"}
        if i in required and getattr(self, required[i]) is None:
            raise ValueError(f"intent {i} cần trường {required[i]}")
        extra = [k for k, owner in SECTION_OWNER.items() if getattr(self, k) is not None and owner != i]
        if extra:  # a section of another intent: the plan was read two ways at once (K3: an LLM filling every field)
            raise ValueError(f"intent {i} không có trường {extra}")
        if i in ("trend", "series") and (self.period is None or self.period.kind != "months"):
            raise ValueError(f"intent {i} cần period kind months")
        if i == "rank" and self.measures and self.measures[0].metric != self.rank.by:
            raise ValueError(f"rank.by={self.rank.by} khác measures[0].metric={self.measures[0].metric}")
        if i == "count_where" and self.measures and self.measures[0].metric != self.threshold.metric:
            raise ValueError(f"threshold.metric={self.threshold.metric} khác measures[0].metric={self.measures[0].metric}")
        ls = self.list_spec
        if ls is not None and ls.condition == "expiring_within" and ls.n is None and not (
                self.period is not None and self.period.kind in ("range", "next_n_days")):
            raise ValueError("expiring_within cần n (số ngày) hoặc period range / next_n_days (khoảng hạn dùng)")
        expected = expected_answer_type(self)
        if self.answer_type is None:
            if expected is None:
                raise ValueError("không suy ra được answer_type, cần ghi rõ")
            self.answer_type = expected
        elif expected is not None and self.answer_type != expected:
            raise ValueError(f"answer_type={self.answer_type} mâu thuẫn với plan (suy ra {expected})")
        return self


def expected_answer_type(p: QueryPlan) -> str | None:
    """The answer type implied by the plan's shape, or None where the shape does not decide it."""
    i = p.intent
    if i == "out_of_scope":
        return "unanswerable"
    if i == "trend":
        return "boolean"
    if i == "list_items":
        return "number" if p.list_spec is not None and p.list_spec.count else "list"
    if i == "count_where" and p.threshold is not None:
        return "percent" if p.threshold.as_share else "number"
    if i == "series":
        return "list"
    if i == "rank" and p.rank is not None:
        r = p.rank
        if r.with_values:
            return "table"
        if r.k != 1:
            return "list"
        return {"day": "date", "month": "date", "hour": "number"}.get(r.entity, "string")
    if not p.measures:
        return None
    if len(p.measures) > 1 or p.measures[0].unit_split:
        return "list"
    metric = p.measures[0].metric
    if metric == "other" and i == "value":
        return None  # what is measured is free text: the LLM must state the answer type
    if i == "share":
        return "percent"
    if i == "compare" and p.compare is not None:
        if p.compare.output == "pct_change":
            return "percent"
        if p.compare.output == "which_more":
            return "string"
        return None if metric in PERCENT_METRICS else "number"
    if metric in PERCENT_METRICS:
        return "percent"
    if metric in DATE_METRICS:
        return "date"
    return "number"


class ResolvedPeriod(_Model):
    start: date
    end: date  # inclusive
    mode: Literal["flow", "stock"] = "flow"  # flow: phát sinh trong kỳ; stock: tình trạng đến hết `end`
    label: str = ""


class ResolvedPlan(_Model):
    """Plan after [C2] (dates) and [C3] (names linked to data values)."""
    plan: QueryPlan
    as_of: date
    period: ResolvedPeriod | None = None
    compare_period: ResolvedPeriod | None = None
    series: list[ResolvedPeriod] = []
    linked: dict[str, str] = {}  # value as written in the question -> value found in the data
    link_scores: dict[str, float] = {}
