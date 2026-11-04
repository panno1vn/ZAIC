"""Every filter of a plan must be grounded in the question. With "filters" required in the generation schema the LLM
stopped dropping filters but began inventing them (K3 run 2, 05/11: 10/123 plans with a filter the question never
names). A filter is grounded when its words are in the question (folded, small typos allowed), or, for a coded field,
when the question has one of its trigger words; a plan with an ungrounded filter is not used.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from rapidfuzz import fuzz

from datamate.contracts import QueryPlan

from .baseline import fold
from .templates import tokens

TRIGGERS = {  # coded fields: words (folded) that must appear for the filter to be asked for
    "shift": ("ca", "sang", "chieu", "toi"),
    "weekday": ("thu", "chu nhat", "cuoi tuan", "ngay le"),
    "order_status": ("huy", "tra", "giao", "hoan thanh", "thanh cong", "doi y"),
    "prescription": ("ke don", "theo don", "toa"),
    "is_warranty": ("bao hanh",),
    "size": ("size", "co", "m", "l", "s"),
}
# coded values that need their own word: "ca" alone is also "cá" (run 04/11: "bán Chả cá chiên được bao nhiêu tiền"
# read as the afternoon shift's revenue)
VALUE_TRIGGERS = {
    "shift": {"morning": ("sang",), "afternoon": ("chieu",)},
    # a weekday needs its name: "thu" alone is also the "thu" of "doanh thu" (04/11: "tuần nayf dthu" planned with a
    # Monday filter)
    "weekday": {"mon": (r"thu (?:2|hai)",), "tue": (r"thu (?:3|ba)",), "wed": (r"thu (?:4|tu)",),
                "thu": (r"thu (?:5|nam)",), "fri": (r"thu (?:6|sau)",), "sat": (r"thu (?:7|bay)", "cuoi tuan"),
                "sun": ("chu nhat", "cn", "cuoi tuan")},
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
        if f.field in VALUE_TRIGGERS and all(v in VALUE_TRIGGERS[f.field] for v in values):
            ok = all(any(re.search(rf"\b{t}\b", q) for t in VALUE_TRIGGERS[f.field][v]) for v in values)
        elif f.field in TRIGGERS:
            ok = any(re.search(rf"\b{re.escape(t)}\b", q) for t in TRIGGERS[f.field])
        elif f.field in NUMERIC:
            ok = all(str(int(v)) in re.sub(r"[.,]", "", question) for v in values if isinstance(v, (int, float)))
        else:
            ok = all(_grounded_text(str(v), tokens, q) for v in values)
        if not ok:
            bad.append(f"{f.field}={f.value}")
    return bad


# Dates and years of a plan must be grounded too. Run 03/11 (T3): for "kể từ khi X lên giá 44.000đ, 14 ngày đầu…"
# (no date: the day of the rise is in the price list) the LLM wrote today as the day of the rise, 4 price-effect
# answers off by hundreds of percent. A day is grounded when the question writes it (d/m, "ngày d tháng m"), or it is
# today / yesterday and the question says so; a month bound when the question writes its month and year.


def _periods(plan: QueryPlan) -> list:
    out = [plan.period] if plan.period else []
    if plan.compare is not None and plan.compare.period is not None:
        out.append(plan.compare.period)
    return out


def _day_grounded(q: str, s: str, as_of: date | None) -> bool:
    """The day is written in the question, with its year when the question writes one there (04/11: "lên giá từ
    ngày 20/05/2025" planned as 20/05/2026, a price effect a year off)."""
    d = date.fromisoformat(s)
    written = re.findall(rf"\b0?{d.day} (?:thang |thg |t )?0?{d.month}(?: (?:nam )?(\d{{4}}))?\b", q)
    if written:
        years = {int(y) for y in written if y}
        return not years or d.year in years
    if as_of is not None and d == as_of and re.search(r"\bhom nay\b", q):
        return True
    return as_of is not None and d == as_of - timedelta(days=1) and bool(re.search(r"\bhom qua\b", q))


def _month_grounded(q: str, y: int, m: int) -> bool:
    return bool(re.search(rf"\b0?{m} (?:nam )?{y}\b", q)) or (
        bool(re.search(rf"\b(?:thang|thg|th|t) 0?{m}\b", q)) and bool(re.search(rf"\b{y}\b", q)))


def _bound_grounded(q: str, s: str, as_of: date | None) -> bool:
    return _day_grounded(q, s, as_of) if len(s) == 10 else _month_grounded(q, int(s[:4]), int(s[5:7]))


def ungrounded_dates(question: str, plan: QueryPlan, as_of: date | None = None) -> list[str]:
    """The explicit days and month bounds of the plan's periods the question does not write."""
    q = fold(question)
    bad = []
    for p in _periods(plan):
        if p.kind in ("month", "this_month", "last_month") and re.search(r"\bquy\b", q):
            bad.append(f"kind={p.kind}")  # "số đơn quý 2/2025" read as February (04/11, twice)
        for name in ("date", "start", "end"):
            v = getattr(p, name)
            if v is not None and not _bound_grounded(q, v, as_of):
                bad.append(f"{name}={v}")
        months = p.months or []
        n = [int(m[:4]) * 12 + int(m[5:7]) for m in months]
        if n and n == list(range(n[0], n[0] + len(n))):
            months = [months[0], months[-1]]  # "từ tháng 8 đến tháng 10": the months between are implied
        bad += [f"months={m}" for m in months if not _bound_grounded(q, m, as_of)]
    return bad


def _year_grounded(q: str, y: int, as_of: date | None) -> bool:
    if re.search(rf"\b{y}\b", q):
        return True
    if as_of is not None and y == as_of.year and re.search(r"\bnam nay\b", q):
        return True
    return as_of is not None and y == as_of.year - 1 and bool(re.search(r"\bnam (?:truoc|ngoai|roi)\b", q))


# What the plan measures must be grounded too. Run 03/11 (T3, 790 questions with the LLM): "số ddown ca chiều…"
# (telex for "đơn") read as revenue, "có bao nhiêu mặt hàng không bán được" read as a list. Revenue needs a money
# word, an order count an order word, a count of listed objects a counting word. The words come from the train
# questions; on 807 hand and LLM plans the check flags misread plans only ("3 món hot nhất" as revenue, "lãi gộp"
# as revenue…).
_MEASURE_WORDS = {
    "revenue": r"\b(?:doanh thu|dthu|dt|revenue|tien|dong|vnd|thu ve|thu duoc|ban duoc|ban ra|ban dat|chi tieu"
               r"|ban gioi|dong gop|chiem|ti trong|ty trong|phan cua)\b",
    "order_count": r"\b(?:don|hoa don|bil|bill|orde|order)\b",
    "quantity": r"\b(?:ban|tieu thu|xuat|chay|hot)\b",  # sold: "còn bao nhiêu viên" is stock (run 04/11)
    # left in stock: "số nhập trừ số bán" read as stock (check_plans 04/11, after the stock metrics)
    "stock_qty": r"\b(?:ton|con|trong kho|het hang)\b",
    # the public rulebook tells "nhà cung cấp chính" (most receipts) from the one bought from for the most money
    "purchase_amount": r"\b(?:tien|gia tri)\b",
    "receipt_count": r"\b(?:phieu|chinh|lan nhap)\b",
    "delivery_count": r"\b(?:giao|dot|cho)\b",
    "gross_profit": r"\b(?:lai|loi)\b",
    "net_profit": r"\b(?:rong|chi phi)\b",
}
_COUNTING = r"\b(?:bao nhieu|bao nhiu|bn|bnhiu|bnhieu|may|dem|so luong|tong so|tong cong)\b"  # not "nhiều" alone
_PERCENT = r"%|\b(?:phan tram|chiem|ti trong|ty trong|ti le|ty le|phan cua|dong gop)\b"
# "nào" lists only after an object ("mặt hàng nào"): "không bán được cái nào" means none at all, and so does
# "bán ko được món nào" (run 04/11: "có tổng cộng mấy mặt hàng ế, bán ko dc món nào" read as a list)
_LISTING = r"\b(?:liet ke|nhung|la gi|ke ten|(?:mat hang|hang|mon|san pham|thuoc|khach|lo) nao)\b"
_NONE_AT_ALL = r"\b(?:khong|ko|chua)\b(?: \w+){0,3} (?:mat hang|hang|mon|san pham|thuoc|cai|lo) nao\b"
# Questions about something the sales metrics do not measure (oracle run 04/11, 790 questions, examples of other
# businesses only: 7 wrong answers, all of them these): stock left ("còn bao nhiêu tuýp", "kho còn tồn"), a unit
# price ("đơn giá bao nhiêu tiền một viên"), purchases ("số nhập trừ số bán"). Product names may hold "tôn" (roofing
# sheet) and "các mặt hàng còn lại" means the other items, so stock needs a phrase, not a word.
_STOCK = r"\b(?:ton kho|con ton|trong kho|kho con|con lai (?:may|bao nhieu|bn)|con (?:bao nhieu|bn|may))\b"
_UNIT_PRICE = r"\b(?:don gia|gia ban)\b"
_MONEY = r"\b(?:doanh thu|dthu|dt|revenue|tien|dong|vnd|thu ve|chi tieu)\b"
_PURCHASE = r"\bnhap\b"
_SALES = {"revenue", "quantity", "order_count"}


def ungrounded_measures(question: str, plan: QueryPlan) -> list[str]:
    """What the plan measures that the question's words do not ask for: a metric without its word, a list where the
    question counts, a count where it lists."""
    t = " ".join(tokens(question))  # telex undone: "ddown" is "don"
    metrics = [m.metric for m in plan.measures] + ([plan.rank.by] if plan.rank else []) + (
        [plan.threshold.metric] if plan.threshold else [])
    bad = [f"metric={m}" for m in dict.fromkeys(metrics) if m in _MEASURE_WORDS and not re.search(_MEASURE_WORDS[m], t)]
    if metrics and set(metrics) <= _SALES:
        bad += [f"asks={what}" for what, words in (("stock", _STOCK), ("purchase", _PURCHASE)) if re.search(words, t)]
    if "revenue" in metrics and re.search(_UNIT_PRICE, t):
        bad.append("asks=unit_price")
    if {"revenue", "quantity"} <= set(metrics) and not re.search(_MONEY, t):
        bad.append("metric=revenue")  # "bán được bao nhiêu ly" counts, "bán được" is no money word then (04/11)
    if "gross_profit" in metrics and re.search(r"\brong\b", t):  # "lợi nhuận ròng" read as gross (check_plans 04/11)
        bad.append("asks=net_profit")
    asks_percent = bool(re.search(_PERCENT, t))
    if plan.intent == "share" and not asks_percent:  # "dthu thuốc kê đơn" read as a share of revenue
        bad.append("intent=share")
    if plan.compare is not None and plan.compare.output == "pct_change" and not asks_percent:
        bad.append("output=pct_change")
    ls = plan.list_spec
    if ls is not None:
        counting, listing = bool(re.search(_COUNTING, t)), bool(re.search(_LISTING, re.sub(_NONE_AT_ALL, " ", t)))
        if ls.count and not counting:
            bad.append("count=true")
        if not ls.count and counting and not listing:
            bad.append("count=false")
    return bad


def drop_ungrounded_years(question: str, plan: QueryPlan, as_of: date | None = None) -> QueryPlan:
    """The plan without the years of month / quarter / Tết periods the question does not state: §2 decides the year
    of "tháng 6" (this year unless after today), not the LLM. A year period keeps its year (it has no other)."""
    q = fold(question)
    changed = {}
    for key, p in (("period", plan.period), ("compare", plan.compare.period if plan.compare else None)):
        if p is None:
            continue
        fix = {}
        if p.kind in ("month", "quarter") and p.year is not None and not _year_grounded(q, p.year, as_of):
            fix["year"] = None
        if p.kind == "tet" and p.lunar_year is not None and not _year_grounded(q, p.lunar_year, as_of):
            fix["lunar_year"] = None
        if fix:
            changed[key] = p.model_copy(update=fix)
    if not changed:
        return plan
    update = {}
    if "period" in changed:
        update["period"] = changed["period"]
    if "compare" in changed:
        update["compare"] = plan.compare.model_copy(update={"period": changed["compare"]})
    return plan.model_copy(update=update)
