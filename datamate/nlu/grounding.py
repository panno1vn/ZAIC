"""Every filter of a plan must be grounded in the question. With "filters" required in the generation schema the LLM
stopped dropping filters but began inventing them (K3 run 2, 05/11: 10/123 plans with a filter the question never
names). A filter is grounded when its words are in the question (folded, small typos allowed), or, for a coded field,
when the question has one of its trigger words; a plan with an ungrounded filter is not used.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from rapidfuzz import fuzz

from datamate.contracts import QueryPlan

from .baseline import fold
from .templates import tokens

TRIGGERS = {  # coded fields: words (folded) that must appear for the filter to be asked for
    "shift": ("ca", "sang", "chieu", "toi"),
    "weekday": ("thu", "chu nhat", "cuoi tuan", "ngay le"),
    "order_status": ("huy", "tra", "giao", "hoan thanh", "thanh cong", "doi y"),
    "prescription": ("ke don", "theo don", "toa", "don bac si"),
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


CODED = frozenset({"channel", "payment_method"})  # = linking.CODED: values linked to a code of synonyms.json


def _coded_grounded(field: str, value: str, question: str) -> bool:
    """A channel / payment value is grounded when the question writes one of its code's synonyms."""
    from . import linking  # linking imports this package's siblings; late import keeps the modules apart
    code = linking.concept(field, value)
    words = linking.synonyms().get(field, {}).get(code, ()) if code else ()
    return any(re.search(rf"\b{re.escape(fold(w))}\b", question) for w in words)


# A status filter of the orders that count anyway (§1: not cancelled, not returned; in delivery counts) on a question
# that names no status only restates the default. The LLM adds it to plain counts and revenue ("hôm qua bán được mấy
# đơn" → order_status = completed): 10 of 25 train questions it read with no plan, 05/11. The metrics take no status
# filter, so such a plan could only abstain; dropped, the plan is the question's.
_STATUS_NAMED = r"\b(?:hoan thanh|thanh cong|xong|dang giao|da giao|dang van chuyen)\b"
_COUNTED = {"completed", "delivering"}


def drop_restated_status(question: str, plan: QueryPlan) -> QueryPlan:
    if re.search(_STATUS_NAMED, fold(question)):
        return plan

    def fix(m):
        kept = [f for f in m.filters if not (f.field == "order_status" and f.op in ("eq", "in")
                                              and set(f.value if isinstance(f.value, list) else [f.value]) <= _COUNTED)]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    update = {"measures": [fix(m) for m in plan.measures]}
    if plan.share_of is not None:
        update["share_of"] = fix(plan.share_of)
    return plan.model_copy(update=update) if update["measures"] != list(plan.measures) or         update.get("share_of") is not plan.share_of else plan


# N34: a filter that only restates the measure (train, 05/11): "tiền khách trả bớt nợ" read as debt_paid with
# payment_method = "bớt nợ" (13 questions), "xe chở được bao nhiêu đợt hàng" as delivery_count with vehicle_model =
# "xe chở" (6). No function takes such a filter, so the plans could only abstain; dropped, the plan is the question's.
# A unit filter on a quantity ("cộng mọi món tính theo ly", 10) is the measure's unit (§3 "bao nhiêu <đơn vị>").
_DEBT_METRICS = {"debt_paid", "debt_added", "debt_total", "debtor_count", "debt_amount"}
_DEBT_WORDS = re.compile(r"^(?:(?:tra|bot|tra bot|thu|ghi|cong) )?no(?: cu)?$|^mua chiu$")
_VEHICLE_WORDS = re.compile(r"^xe(?: (?:cho|cho hang|giao|giao hang|hang))?$")


# §6 Sửa xe: the average ticket leaves warranty tickets out already, warranty counts and rates are about them: a
# warranty filter on them only restates the metric (public 06/11, "phiếu có thu tiền … trung bình 1 phiếu" read with
# is_warranty = false, which "bảo hành" does not ground; warranty_rate under is_warranty = true would divide by 0)
_WARRANTY_RESTATED = {("avg_ticket_value", False), ("warranty_count", True), ("warranty_rate", True)}


def _restates(metric: str, f) -> bool:
    if f.field == "is_warranty" and isinstance(f.value, bool) and f.op == "eq":
        return (metric, f.value) in _WARRANTY_RESTATED
    if metric in _DEBT_METRICS and f.field == "payment_method" and f.op == "eq" and isinstance(f.value, str):
        from . import linking  # late import, as in _coded_grounded
        if linking.concept("payment_method", f.value) == "debt":  # "khách trả nợ" read with the code "debt" (run10)
            return True
    if isinstance(f.value, (list, bool)) or f.op not in ("eq", "in"):
        return False
    v = fold(str(f.value)).strip()
    return (metric in _DEBT_METRICS and f.field == "payment_method" and bool(_DEBT_WORDS.match(v))) or (
        metric == "delivery_count" and f.field == "vehicle_model" and bool(_VEHICLE_WORDS.match(v)))


def drop_restated_metric(plan: QueryPlan) -> QueryPlan:
    def fix(m):
        kept = [f for f in m.filters if not _restates(m.metric, f)]
        update = {}
        units = [f for f in kept if m.metric == "quantity" and f.field == "unit" and f.op == "eq"
                 and isinstance(f.value, str)]
        if len(units) == 1 and (m.unit is None or fold(m.unit) == fold(units[0].value)):
            update["unit"] = m.unit or units[0].value
            kept = [f for f in kept if f is not units[0]]
        if len(kept) < len(m.filters):
            update["filters"] = kept
        return m.model_copy(update=update) if update else m
    measures = [fix(m) for m in plan.measures]
    share_of = fix(plan.share_of) if plan.share_of is not None else None
    if measures == list(plan.measures) and share_of is plan.share_of:
        return plan
    return plan.model_copy(update={"measures": measures, "share_of": share_of})


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
    whole = {id(f) for f in (plan.share_of.filters if plan.share_of else [])}
    bad = []
    for f in filters:
        values = f.value if isinstance(f.value, list) else [f.value]
        if id(f) in whole and f.field == "product_group" and all(
                any(len(w) >= 3 and w in tokens for w in fold(str(v)).split()) for v in values):
            continue  # the whole of a share named by a word of its group ("% số bịch bỉm": the group "bỉm tã", §6)
        if f.field in VALUE_TRIGGERS and all(v in VALUE_TRIGGERS[f.field] for v in values):
            ok = all(any(re.search(rf"\b{t}\b", q) for t in VALUE_TRIGGERS[f.field][v]) for v in values)
        elif f.field in TRIGGERS:
            ok = any(re.search(rf"\b{re.escape(t)}\b", q) for t in TRIGGERS[f.field])
        elif f.field in CODED:  # the linker's synonyms: "tm", "tiền tươi" are cash (05/11: 3 of 25 plans lost)
            ok = all(_coded_grounded(f.field, str(v), q) or _grounded_text(str(v), tokens, q) for v in values)
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
    written = {f"{y:04d}-{m:02d}" for m, y in stated_months(question)}  # "th 12/25" is 2025-12 (run10, 06/11)
    bad = []

    def grounded(v: str) -> bool:
        return v in written or _bound_grounded(q, v, as_of)

    for p in _periods(plan):
        if p.kind in ("month", "this_month", "last_month") and re.search(r"\bquy\b", q):
            bad.append(f"kind={p.kind}")  # "số đơn quý 2/2025" read as February (04/11, twice)
        for name in ("date", "start", "end"):
            v = getattr(p, name)
            if v is not None and not grounded(v):
                bad.append(f"{name}={v}")
        months = p.months or []
        n = [int(m[:4]) * 12 + int(m[5:7]) for m in months]
        if n and n == list(range(n[0], n[0] + len(n))):
            months = [months[0], months[-1]]  # "từ tháng 8 đến tháng 10": the months between are implied
        bad += [f"months={m}" for m in months if not grounded(m)]
    return bad


def _year_grounded(q: str, y: int, as_of: date | None, short: frozenset[int] = frozenset()) -> bool:
    """`short`: years the question writes in two digits ("th 6/25"). run10 (06/11) dropped them as unstated, and §2
    then put "tháng 6" in this year: 14 answers a year off."""
    if y in short or re.search(rf"\b{y}\b", q):
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
    # run10 (06/11): "doanhthu" written as one word; an amount with its unit ("từ 40tr trở lên"), never "k" alone,
    # which is also "không"
    "revenue": r"\b(?:doanh thu|doanhthu|dthu|dt|revenue|tien|dong|vnd|thu ve|thu duoc|ban duoc|ban ra|ban dat|chi tieu"
               r"|ban gioi|dong gop|chiem|ti trong|ty trong|phan cua|\d+ (?:tr|trieu|cu|k|nghin|ngan))\b",
    # run10: "đh" for "đơn hàng" (14 of 23 questions refused), "o đờ" for "order"; §3 "giờ cao điểm" counts orders
    "order_count": r"\b(?:don|hoa don|bil|bill|orde|order|dh|o do|gio cao diem)\b",
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
    # K1 (06/11): the 10 train answers Qwen3-14B got wrong, each through every other gate
    if plan.intent == "value" and _part_and_whole(plan) and not _asks_several(t):
        bad.append(f"measures={len(plan.measures)}")  # "tổng cộng mấy ly size M, cộng tất cả các món" as M + all
    stated = stated_k(question)
    if plan.rank is not None and stated is not None and plan.rank.k != stated:
        bad.append(f"k={plan.rank.k}")  # "3 khách nào nợ nhiều nhất" with k left at its default 1
    # §6 Cửa hàng điện thoại, misread on a public phone shop (06/11) once its figures had hints
    if "amount_due_total" in metrics and re.search(r"\b(?:gop|tra gop|no|chua tra)\b", t):
        bad.append("metric=amount_due_total")  # "hợp đồng trả góp còn lại bao nhiêu tiền chưa góp": a debt
    if plan.intent == "value" and asks_percent and set(metrics) & {"trade_in_amount", "amount_due_total"}:
        bad.append("asks=percent")  # "bao nhiêu % đơn có thu máy cũ" read as the trade-in total
    if "warranty_count" in metrics and re.search(r"\b(?:may ban|ban ra)\b", t):
        bad.append("asks=phones_sold")  # "máy bán tháng 8 đã mang lại bảo hành": phones, not visits of the month
    if "avg_order_value" in metrics and re.search(r"\bphai tra\b", t):
        bad.append("asks=amount_due")  # §6: "khách phải trả" is after discount and trade-in, not the revenue
    if "overdue_installment_count" in metrics and (re.search(r"\b(?:may|bao nhieu|bn|bnhiu) ky\b", t) or any(
            f.field == "customer" for m in plan.measures for f in m.filters)):
        bad.append("asks=periods")  # "khách X góp tới hạn mấy kỳ": periods of one customer, not customers
    if "overdue_installment_count" in metrics and (re.search(r"\btien\b", t) or not re.search(
            r"\b(?:khach|nguoi|ngui)\b", t)):
        bad.append("asks=overdue_amount")  # "tiền góp quá hạn khách chưa trả là bao nhiêu": money, not customers
    if plan.intent == "share" and plan.share_of is None and re.search(r"\b(?:tien ban may|dthu may|doanh thu may)\b", t):
        bad.append("share_of=phones")  # "% tiền bán máy": the phones' revenue, not the shop's with accessories
    if plan.intent == "value" and "amount_due_total" in metrics and len(plan.measures) > 1 and not _asks_several(t):
        bad.append(f"measures={len(plan.measures)}")  # "khách phải trả, sau khi trừ bớt và máy cũ": one figure
    months = stated_months(question)
    if (plan.compare is not None and plan.compare.kind == "same_period_last_year" and not re.search(_LAST_YEAR, t)
            and len({y for _, y in months} | {int(y) for y in re.findall(r"\b20\d\d\b", t)}) < 2):
        bad.append("compare=same_period_last_year")  # "ca chiều hơn hay kém ca sáng" compared with last year
    if plan.compare is not None and plan.compare.kind == "previous" and _year_over_year(months):
        bad.append("compare=previous")  # "th 6/26 so với th 6/25" read as June against May (run10, 06/11)
    return bad


def stated_months(question: str) -> list[tuple[int, int]]:
    """(month, year) the question writes as M/YYYY or M/YY ("th 6/26" is June 2026)."""
    out = []
    for m, y in re.findall(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{4}|\d{2})(?![\d/])", _plain(question)):
        if 1 <= int(m) <= 12 and (len(y) == 4 or 20 <= int(y) <= 35):  # "ngày 6/12" is no month of 2012
            out.append((int(m), int(y) if len(y) == 4 else 2000 + int(y)))
    return out


def _year_over_year(months: list[tuple[int, int]]) -> bool:
    """The same month of two different years: compared with last year's, never with the month before."""
    return any(a[0] == b[0] and a[1] != b[1] for a in months for b in months)


# several figures asked: two question words, or a word that splits the answer ("mỗi loại", "lần lượt", "hai số")
_ASK = r"\b(?:bao nhieu|bao nhiu|bnhiu|bn|may)\b"
_SPLIT = r"\b(?:lan luot|moi (?:loai|ben|ben|thu|cai|nhom|kenh|hinh thuc)|hai so|ca hai|tung (?:loai|ben|thu)|rieng)\b"
_LAST_YEAR = r"\bnam (?:truoc|trc|ngoai|roi|qua|kia)\b|\bcung ky\b"


def _part_and_whole(plan: QueryPlan) -> bool:
    """Two measures of one metric, the filters of one a strict part of the other's: a part and its whole."""
    keys = [(m.metric, {(f.field, f.op, str(f.value)) for f in m.filters}) for m in plan.measures]
    return any(a[0] == b[0] and b[1] < a[1] for a in keys for b in keys)


def _asks_several(t: str) -> bool:
    return len(re.findall(_ASK, t)) >= 2 or bool(re.search(_SPLIT, t))


_K_OBJECT = (r"(?:khach(?: hang)?|mon|mat hang|san pham|sp|hang|nhan vien|nv|tho|nha cung cap|ncc|xe|dong xe|loai|"
             r"nhom(?: hang)?|thuoc|nguoi|(?:ngay|thang|tuan|gio) nao)")
_K_TIME = re.compile(r"\b(?:thang|ngay|quy|tuan|nam|thu|gio|lan|tet|so)\s*$")


def _plain(text: str) -> str:
    """Lower case without diacritics, punctuation kept (a date's "/" tells its numbers from a count)."""
    s = unicodedata.normalize("NFD", str(text).lower().replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def stated_k(question: str) -> int | None:
    """How many objects a ranking question asks for, when it says so: "top 5", "3 khách nào", "5 món bán chạy".
    A number inside a date ("27/10 khách nào") or after a time word ("tháng 3 khách nào") is no count; one after a
    date is ("27/10/2025, 3 khách nào")."""
    q = _plain(question)
    if m := re.search(r"\btop\s*(\d{1,2})\b", q):
        return int(m.group(1))
    for m in re.finditer(rf"(?<![\d/.:-])\b(\d{{1,2}})\s+{_K_OBJECT}\b", q):
        if not _K_TIME.search(q[:m.start()]):
            return int(m.group(1))
    return None


_EACH = re.compile(r"\b(?:bang|tung|moi|cac|tat ca)\b")


def widen_each_table(question: str, plan: QueryPlan) -> QueryPlan:
    """A table of every object ("bảng hoa hồng từng thợ", "bảng … mọi thợ") read with k at 1, the default, gives a
    one-row table (public 06/11, two such answers). When the question states no count, k is every object."""
    r = plan.rank
    if r is None or not r.with_values or r.k != 1 or stated_k(question) is not None or not _EACH.search(fold(question)):
        return plan
    return plan.model_copy(update={"rank": r.model_copy(update={"k": None})})


def written_last_year(plan: QueryPlan) -> QueryPlan:
    """"Dthu th 3/26 tăng trưởng bao nhiêu % so th 3/25" planned as compare previous with the compared month written
    (3/2025): previous ignores the written period and takes February (run10 06/11: 4 plans, refused by the gate of
    `_year_over_year`). The month of another year the plan writes is the period compared with."""
    c, p = plan.compare, plan.period
    if c is None or c.kind != "previous" or c.period is None or p is None or c.period.kind != "month" \
            or p.kind != "month" or c.period.year is None or p.year is None or c.period.year == p.year:
        return plan
    return plan.model_copy(update={"compare": c.model_copy(update={"kind": "period"})})


def whole_not_part(plan: QueryPlan) -> QueryPlan:
    """A share whose whole is written as its very part ("dthu đơn bán tại quầy chiếm bn % tổng dthu của shop" with
    share_of = the counter's revenue: 100% whatever the data, run10 06/11, the shop's right answer 89.26%): the whole is
    the shop's, as a share with no share_of reads (§1)."""
    if plan.intent == "share" and plan.share_of is not None and plan.measures and plan.share_of == plan.measures[0]:
        return plan.model_copy(update={"share_of": None})
    return plan


def count_as_value(plan: QueryPlan) -> QueryPlan:
    """"Đếm phiếu sửa xe được mấy phiếu" written as the orders with at least one order (or ticket) in them: every
    order, so the count of orders itself (public 06/11). Only that bound: ≥ 1 / > 0 on an order's own count."""
    t = plan.threshold
    if plan.intent != "count_where" or t is None or t.entity != "order" or t.as_share \
            or t.metric not in ("order_count", "ticket_count") or (t.op, t.value) not in (("gte", 1), ("gt", 0)):
        return plan
    filters = plan.measures[0].filters if plan.measures else []
    return QueryPlan.model_validate({"intent": "value", "period": plan.period.model_dump(exclude_none=True),
                                     "measures": [{"metric": t.metric, "filters": [f.model_dump() for f in filters]}]})


RATES = frozenset({"cancel_rate", "warranty_rate"})  # metrics that are already a percent of a whole the rulebook fixes


def rate_as_value(plan: QueryPlan) -> QueryPlan:
    """"Tháng này đơn huỷ chiếm bao nhiêu % toàn bộ đơn" written as a share of the cancel rate (run11 07/11): the cancel
    rate is that percent already (§1 "phần trăm đơn huỷ trong mọi đơn đặt trong kỳ"), so the value of the rate. Only
    without a denominator of the plan's own (share_of) and when every measure is such a rate."""
    if plan.intent != "share" or plan.share_of is not None or not plan.measures \
            or any(m.metric not in RATES for m in plan.measures):
        return plan
    return plan.model_copy(update={"intent": "value"})


_MONEY_UNIT = {"cu": 1_000_000, "trieu": 1_000_000, "tr": 1_000_000, "k": 1_000, "nghin": 1_000, "ngan": 1_000}
_AMOUNT = re.compile(r"\b(\d+)(?: (\d+))? (cu|trieu|tr|k|nghin|ngan)\b")


def scale_money(question: str, plan: QueryPlan) -> QueryPlan:
    """A money bound the question writes with its unit ("từ 10 củ trở lên": 10 million, "trên 500k") and the plan
    writes bare (run9: days with revenue ≥ 10 đồng, i.e. every day). Only when the plan's number is the question's
    number without its unit."""
    t = plan.threshold
    if t is None or t.metric not in ("revenue", "purchase_amount", "debt_amount"):
        return plan
    for whole, part, unit in _AMOUNT.findall(fold(question)):
        n = float(f"{whole}.{part}") if part else float(whole)  # "1 5 trieu" is 1,5 million once folded
        if t.value == n and _MONEY_UNIT[unit] > 1:
            return plan.model_copy(update={"threshold": t.model_copy(update={"value": n * _MONEY_UNIT[unit]})})
    return plan


def _age_bounds(text: str, previous_upper: float | None) -> list[dict] | None:
    """One debt-age group written in words ("0–7 ngày", "8-15", "trên 15", "15+") as numeric bounds; None if unread."""
    t = _plain(text)
    if m := re.search(r"(\d+)\s*[–\-—]\s*(\d+)", t):
        return [{"field": "debt_age_days", "op": "gte", "value": float(m[1])},
                {"field": "debt_age_days", "op": "lte", "value": float(m[2])}]
    if m := re.search(r"(?:tren|qua|hon|>)\s*(\d+)", t):
        return [{"field": "debt_age_days", "op": "gt", "value": float(m[1])}]
    if m := re.search(r"(\d+)\s*\+", t):  # "15+" after "8–15" starts above 15
        n = float(m[1])
        return [{"field": "debt_age_days", "op": "gt" if previous_upper == n else "gte", "value": n}]
    if m := re.search(r"(?:duoi|<)\s*(\d+)", t):
        return [{"field": "debt_age_days", "op": "lt", "value": float(m[1])}]
    return None


def split_debt_ages(plan: QueryPlan) -> QueryPlan:
    """"Nợ còn lại chia theo tuổi nợ 0–7, 8–15 và trên 15 ngày" (train 5 questions, answered as a list; public 06/11
    6 more), written as one debt measure with a word filter per group, or a measure per group: one debt_total per
    group in the question's order, each with the group's numeric bounds (§4 "tuổi nợ")."""
    debt = {"debt_total", "debt_amount"}
    ms = list(plan.measures)
    if plan.intent != "value" or not ms or any(m.metric not in debt for m in ms):
        return plan
    groups = [(m, f) for m in ms for f in m.filters if f.field == "debt_age_days" and isinstance(f.value, str)]
    if len(groups) < 2:
        return plan
    out, upper = [], None
    for m, f in groups:
        bounds = _age_bounds(f.value, upper)
        if bounds is None:
            return plan
        upper = next((b["value"] for b in bounds if b["op"] == "lte"), upper)
        rest = [x.model_dump(exclude_none=True) for x in m.filters if x.field != "debt_age_days"]
        metric = "debt_amount" if any(x["field"] == "customer" for x in rest) else "debt_total"
        out.append({"metric": metric, "filters": rest + bounds})
    raw = plan.model_dump(mode="json", exclude_none=True)
    raw["measures"] = out
    raw.pop("answer_type", None)
    return QueryPlan.model_validate(raw)


_NEW_PRICE = re.compile(r"\blen(?: gia)?\s+(\d{1,3}(?:[.,]\d{3})+|\d{4,})\s*(?:d|dong|vnd)\b")


def anchor_by_price(question: str, plan: QueryPlan, as_of: date | None = None) -> QueryPlan:
    """"Từ hồi Trà vải (L) lên giá 47.000đ, so 30 ngày kể từ ngày đổi giá…" names the day by the new price, not by a
    date (§5 "hiệu ứng tăng giá"); run10 (06/11): the LLM wrote a day the question does not give, 6 questions refused.
    A days_from period whose day the question does not write takes the price as its anchor, as the train hand plans
    do ({"kind": "days_from", "anchor_price": 97500, "n": 30})."""
    p = plan.period
    if p is None or p.kind != "days_from" or p.date is None or _day_grounded(fold(question), p.date, as_of):
        return plan
    prices = {int(re.sub(r"[.,]", "", m)) for m in _NEW_PRICE.findall(_plain(question))}
    if len(prices) != 1:
        return plan
    return plan.model_copy(update={"period": p.model_copy(update={"date": None, "anchor_price": float(prices.pop())})})


_WEEKDAY_WORDS = re.compile(r"\bthu (?:2|3|4|5|6|7|hai|ba|tu|nam|sau|bay)\b|\bchu nhat\b|\bcuoi tuan\b|\bcn\b")


def drop_month_as_weekday(question: str, plan: QueryPlan) -> QueryPlan:
    """"T5/2025" is May 2025: a weekday never comes with a year. run10 (06/11): read as Friday or Thursday in 6 plans.
    The weekday filter is dropped when the question has no weekday word besides such "T<month>/<year>"."""
    if not re.search(r"\bt\s*\d{1,2}\s*/\s*\d{2,4}\b", _plain(question)) or _WEEKDAY_WORDS.search(fold(question)):
        return plan

    def fix(m):
        kept = [f for f in m.filters if f.field != "weekday"]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) for m in plan.measures]
    return plan if measures == list(plan.measures) else plan.model_copy(update={"measures": measures})


_SHORT_YEAR = re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{2})(?![\d/])")


def month_of_short_year(question: str, plan: QueryPlan) -> QueryPlan:
    """"3/26" is month 3 of 2026: a Vietnamese day is written before its month, so it cannot be day 3 of month 26.
    The LLM read it as the day 2026-03-26 (public 06/11); that exact reading becomes the month."""
    p = plan.period
    if p is None or p.kind != "day" or p.date is None:
        return plan
    try:
        d = date.fromisoformat(str(p.date))
    except ValueError:
        return plan
    for m, yy in _SHORT_YEAR.findall(question):
        if int(m) == d.month and int(yy) == d.day and d.year == 2000 + int(yy):
            return plan.model_copy(update={"period": p.model_copy(update={"kind": "month", "date": None,
                                                                            "year": d.year, "month": d.month})})
    return plan


def drop_ungrounded_years(question: str, plan: QueryPlan, as_of: date | None = None) -> QueryPlan:
    """The plan without the years of month / quarter / Tết periods the question does not state: §2 decides the year
    of "tháng 6" (this year unless after today), not the LLM. A year period keeps its year (it has no other)."""
    q = fold(question)
    written = stated_months(question)
    short = frozenset(y for _, y in written)
    changed = {}
    for key, p in (("period", plan.period), ("compare", plan.compare.period if plan.compare else None)):
        if p is None:
            continue
        fix = {}
        if p.kind in ("month", "quarter") and p.year is not None and not _year_grounded(q, p.year, as_of, short):
            fix["year"] = None
        if p.kind == "month" and p.year is None:  # "th 6/25" planned without a year: the one the question writes
            years = {y for m, y in written if m == p.month}
            if len(years) == 1:
                fix["year"] = years.pop()
        if p.kind == "tet" and p.lunar_year is not None and not _year_grounded(q, p.lunar_year, as_of, short):
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
