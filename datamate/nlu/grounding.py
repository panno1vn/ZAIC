"""Every filter of a plan must be grounded in the question. With "filters" required in the generation schema the LLM
stopped dropping filters but began inventing them (K3 run 2, 05/11: 10/123 plans with a filter the question never
names). A filter is grounded when its words are in the question (folded, small typos allowed), or, for a coded field,
when the question has one of its trigger words; a plan with an ungrounded filter is not used.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta

from rapidfuzz import fuzz

from datamate.contracts import QueryPlan
from datamate.contracts.plan import DATE_METRICS

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


# N101. §6 Điện thoại "khách phải trả là tiền của đơn sau bớt và sau trừ máy cũ": a question asking what customers paid
# after the discount and the trade-in, read with a category made of those deduction words, or
# "trade_in" (public run11, 2 questions, the retry the same): the words of the metric's own deductions
_DUE_METRICS = {"amount_due_total", "avg_amount_due", "trade_in_amount"}
_DEDUCTION_WORDS = re.compile(r"\b(?:tru|bot|thu lai|giam gia)\b|trade.?in")


def _restates(metric: str, f) -> bool:
    if f.field == "is_warranty" and isinstance(f.value, bool) and f.op == "eq":
        return (metric, f.value) in _WARRANTY_RESTATED
    if metric in _DUE_METRICS and f.field in ("category", "product_group", "product", "other") and f.op == "eq" \
            and isinstance(f.value, str) and _DEDUCTION_WORDS.search(fold(f.value)):
        return True
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
    # N79: the part repeats the whole's group ("bỉm size XL chiếm bao nhiêu % số bịch bỉm": product_group "bỉm tã" on
    # both, §6 Mẹ và bé divides by every "bỉm tã"); public 08/11, 3 such first plans refused, the retries lost the group
    whole_keys = {(f.field, f.op, str(f.value)) for f in (plan.share_of.filters if plan.share_of else [])}
    bad = []
    for f in filters:
        values = f.value if isinstance(f.value, list) else [f.value]
        if (id(f) in whole or (f.field, f.op, str(f.value)) in whole_keys) and f.field == "product_group" and all(
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
    if as_of is not None and d == as_of and re.search(r"\b(?:hom nay|hnay|tu nay|hien nay|hien tai|bay gio)\b", q):
        return True  # "từ nay đến hết ngày X" starts today too (N99)
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
        if p.kind in ("this_month", "last_month") and written and as_of is not None:
            # N95: "<tháng> tiền bán ca chiều" read as this month (a full public run 08/11; the run before had read August,
            # greedy decoding varies): a relative month that is none of the months the question writes
            y, m = (as_of.year, as_of.month) if p.kind == "this_month" else (
                (as_of.year, as_of.month - 1) if as_of.month > 1 else (as_of.year - 1, 12))
            if f"{y:04d}-{m:02d}" not in written:
                bad.append(f"kind={p.kind}")
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
    # N109: §3 "ngày đắt khách nhất" is the day with the most orders
    "order_count": r"\b(?:don|hoa don|bil|bill|orde|order|dh|o do|gio cao diem|dat khach)\b",
    "quantity": r"\b(?:ban|tieu thu|xuat|chay|hot|best)\b",  # sold ("best seller", N138): "còn bao nhiêu viên" is stock (run 04/11)
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


_WHICH_TIME = r"\b(?:thang|ngay|tuan|quy|nam|thu|gio|khung gio) nao\b"
# N79 (public 08/11): parts a plan may leave out that the question asks. Ranking words as public writes them too:
# "nhứt" / "nhut", "nhta", "caonhất", "giờ cao điểm" (every one of the 288 train rank questions has nhất, top or xếp)
_SUPERLATIVE = r"(?:nh[au]t|nhta)\b|\btop\b"
# the rulebook's ranking terms without "nhất" too: §5 "nhà cung cấp chính", §3 "giờ cao điểm", "bán chạy"
_RANK_WORDS = _SUPERLATIVE + (r"|\b(?:xep|cao diem|dung dau|hang dau|dan dau|best|hot|ban chay"
                              r"|(?:nha cung cap|ncc) chinh)\b")
_AGED = r"\b(?:qua|tren|hon|lau hon)\s+\d+\s*ngay\b"  # "nợ ở các đơn đã đặt quá 7 ngày" (§4 tuổi nợ)
_PERIODS = r"\b(?:may|bao nhieu|bao nhiu|bn|bnhiu|bnhieu|nhieu) ky\b"  # "góp tới hạn mấy kỳ" (§6 Điện thoại)


# N84: typing noise of public questions on the very words the measure gates look for: a "g" added after a final "n"
# ("đơng", "tiềng", "báng"), "c" typed "t" ("đượt"), a word glued to the next ("nhiềuđơn"). Read with their accents only:
# folded, "dong", "tieng", "bang" are other words (đồng, tiếng, bảng).
_NOISE = ((re.compile(r"\b(đơn|tiền|bán)g\b"), r"\1"), (re.compile(r"\bđượt\b"), "được"),
          (re.compile(r"(nhiều|nhiêu|mấy)(đơn|tiền)"), r"\1 \2"))


def denoised(question: str) -> str:
    q = unicodedata.normalize("NFC", question.lower())
    for pattern, repl in _NOISE:
        q = pattern.sub(repl, q)
    return q


def ungrounded_measures(question: str, plan: QueryPlan) -> list[str]:
    """What the plan measures that the question's words do not ask for: a metric without its word, a list where the
    question counts, a count where it lists."""
    t = " ".join(tokens(denoised(question)))  # telex undone: "ddown" is "don"
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
        bad.append("metric=amount_due_total")  # the money still unpaid on instalment contracts: a debt
    if plan.intent == "value" and asks_percent and set(metrics) & {"trade_in_amount", "amount_due_total"}:
        bad.append("asks=percent")  # "bao nhiêu % đơn có thu máy cũ" read as the trade-in total
    if "warranty_count" in metrics and re.search(r"\b(?:may ban|ban ra)\b", t):
        bad.append("asks=phones_sold")  # "máy bán tháng 8 đã mang lại bảo hành": phones, not visits of the month
    if "avg_order_value" in metrics and re.search(r"\bphai tra\b", t):
        bad.append("asks=amount_due")  # §6: "khách phải trả" is after discount and trade-in, not the revenue
    if re.search(_PERIODS, t) or ("overdue_installment_count" in metrics and any(
            f.field == "customer" for m in plan.measures for f in m.filters)):
        # "khách X góp tới hạn mấy kỳ": a number of instalments, which no metric counts (overdue_installment_count
        # counts customers); N79 public 08/11: read as the customer's debt in money
        bad.append("asks=periods")
    if "overdue_installment_count" in metrics and (re.search(r"\btien\b", t) or not re.search(
            r"\b(?:khach|nguoi|ngui)\b", t)):
        bad.append("asks=overdue_amount")  # the overdue instalment money customers still owe: money, not customers
    if plan.intent == "share" and (plan.share_of is None or not plan.share_of.filters) and re.search(
            r"\b(?:tien ban may|dthu may|doanh thu may)\b", t):
        # "% tiền bán máy": the phones' revenue, not the shop's with accessories (a whole with no filter is the shop's
        # too: N79 public 08/11, the retry wrote share_of revenue with no filter)
        bad.append("share_of=phones")
    if set(metrics) & _DEBT_METRICS and re.search(_AGED, t) and not any(
            f.field == "debt_age_days" for m in plan.measures for f in m.filters):
        bad.append("asks=debt_age")  # N79: "nợ ở các đơn đã đặt quá 7 ngày" read as the whole debt
    if plan.intent == "rank" and not re.search(_RANK_WORDS, t):
        bad.append("intent=rank")  # N79: "<tháng> khách nữ mua bnhiu tiền" read as a top 5; "có mấy mặt hàng cháy hàng"
    r = plan.rank
    if r is not None and r.entity == "month" and plan.period is not None and plan.period.kind == "month":
        bad.append("asks=months")  # N97: months ranked over one month can only give that month
    if (r is not None and r.k == 1 and not r.with_values and stated_k(question) is None
            and re.search(_EVERY_OBJECT, t) and not re.search(_SUPERLATIVE, t)):
        bad.append("asks=every")  # N79: "bảng hoa hồng của mọi thợ, xếp từ cao xuống thấp" read as the first thợ
    if plan.intent == "value" and "amount_due_total" in metrics and len(plan.measures) > 1 and not _asks_several(t):
        bad.append(f"measures={len(plan.measures)}")  # "khách phải trả, sau khi trừ bớt và máy cũ": one figure
    months = stated_months(question)
    if (plan.compare is not None and plan.compare.kind == "same_period_last_year" and not re.search(_LAST_YEAR, t)
            and len({y for _, y in months} | {int(y) for y in re.findall(r"\b20\d\d\b", t)}) < 2):
        bad.append("compare=same_period_last_year")  # "ca chiều hơn hay kém ca sáng" compared with last year
    if plan.compare is not None and plan.compare.kind == "previous" and _year_over_year(months):
        bad.append("compare=previous")  # "th 6/26 so với th 6/25" read as June against May (run10, 06/11)
    # N139b: "lô X gần hết hạn nhất có hạn dùng ngày nào" asks a date, the plan nearest_expiry (§5, the prompt's own
    # example); train 4 such plans refused here
    if plan.intent in ("series", "value") and re.search(_WHICH_TIME, t) and re.search(r"\bnhat\b", t) \
            and not (metrics and set(metrics) <= DATE_METRICS):
        bad.append("asks=which_time")  # N78: which of three months had the highest revenue, read as the series
    return bad


# N83: a question about a quality of people or suppliers the data does not record ("khách thân thiện nhất", "thợ nhiệt
# tình nhất", "nhà cung cấp uy tín", "nhân viên có tận tâm không"): it names who but no figure at all, and no term the
# rulebook defines (§3 "trung thành", "sộp", "hay đổi ý", "chăm chỉ"…, §5 "nhà cung cấp chính"). Train: the 5
# questions of 3000 this reads are all unanswerable, and no other.
_WHO = r"\b(?:khach(?: hang)?|nhan vien|nv|tho|nha cung cap|ncc|nguoi)\b"
_ANY_FIGURE = "|".join([*_MEASURE_WORDS.values(), _COUNTING, _PERCENT, _MONEY, _STOCK, _PURCHASE,
                        r"\b(?:mua|ban|don|dh|no|chiu|gop|nhap|ton|lan|ngay|so|luong|doanh|tien|hoa hong|luot|xe|phieu"
                        r"|gio|cao diem|tra|huy|doi y)\b"])
_DEFINED_TERMS = r"\b(?:trung thanh|sop|doi y|ua chuong|cham chi|dat khach|cao diem|ban chay|ban gioi|chinh|loi|lai|hot)\b"


def customer_trait_not_recorded(question: str, readme: str) -> bool:
    """N89. A question by the customers' gender ("khách nữ chiếm bao nhiêu % doanh thu") or street ("khách ở đường
    Trần Não") in a shop whose README names no such column, or names it empty ("Giới tính: cột trống"): the shop does
    not record it (§7). Train: the 10 such questions of 3000 are all unanswerable, every one in a shop whose README
    names neither. Gender read with accents: "khách năm 2025" folds as "khách nam" does."""
    q = unicodedata.normalize("NFC", question.lower())
    t = " ".join(tokens(question))
    gender = bool(re.search(r"\bkhách(?: hàng)? (?:nữ|nam)\b(?!\s*(?:\d|nay|ngoái|trước))", q)
                  or re.search(r"\bkhach(?: hang)? nu\b|\bgioi tinh\b", t))
    street = bool(re.search(r"\bkhach(?: hang)?(?: nha)?(?: o)? duong\b|\bnha o duong\b|\bdia chi\b", t))
    if not gender and not street:
        return False
    lines = [unicodedata.normalize("NFC", l.lower()) for l in readme.splitlines()]

    def recorded(word: str) -> bool:
        return any(word in l and not re.search(r"cột trống|không có dữ liệu", l) for l in lines)
    return (gender and not recorded("giới tính")) or (street and not recorded("địa chỉ"))


# N112: a product's quality ("chất lượng tốt nhất", "ngon nhất"), which no file records (§7)
_PRODUCT_QUALITY = r"\b(?:ngon nhat|chat luong(?: tot| cao)? nhat|chat luong tot)\b"


def subjective_quality(question: str) -> bool:
    t = " ".join(tokens(question))
    if re.search(_PRODUCT_QUALITY, t):
        t = re.sub(r"\bchat luong\b", " ", t)  # folded "chất lượng" is no "số lượng"
    elif not re.search(_WHO, t):
        return False
    return not re.search(_ANY_FIGURE, t) and not re.search(_DEFINED_TERMS, t)


_DUE_ASKED = re.compile(r"\bngay phai tra\b")
_HOW_MANY_ORDERS = re.compile(r"\b(?:may|bao nhieu|bnhiu|bn|so) don\b")
_AFTER_TODAY = re.compile(r"\b(?:muon hon|sau|tre hon)\s+(?:hom nay|hnay|bua nay|bua ni)\b")


def due_date_count_plan(question: str, as_of: date) -> QueryPlan | None:
    """N113. How many credit orders, by today, have a due day in a given month or after today: the
    credit orders placed by today whose due day (the README's "Ngày phải trả") is in that month, or after today
    (internal metric due_order_count). The month is usually after today, so it is no period of the plan: the plan's
    period is "until today" (orders placed by then). The LLM reads none of the 6 public questions (4 no plan, 2 an
    order count with the due day as payment methods). Train has no such question; the metric needs the due day mapped
    (from_readme.enrich), else no answer."""
    t = " ".join(tokens(question))
    if not _DUE_ASKED.search(t) or not _HOW_MANY_ORDERS.search(t):
        return None
    months, after = stated_months(question), bool(_AFTER_TODAY.search(t))
    if after == bool(months) or len(months) > 1:
        return None
    from datamate.metrics.debt import DUE_NOTE
    value = "today" if after else f"{months[0][1]:04d}-{months[0][0]:02d}"
    return QueryPlan.model_validate({
        "intent": "value", "period": {"kind": "until", "date": as_of.isoformat()}, "answer_type": "number",
        "measures": [{"metric": "due_order_count", "filters": [
            {"field": "other", "op": "gt" if after else "eq", "value": value, "note": DUE_NOTE}]}]})


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
_EVERY_OBJECT = rf"\b(?:moi|tung|tat ca(?: cac)?|toan bo(?: cac)?) {_K_OBJECT}\b"  # "mọi thợ", "từng nhân viên"


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


_ASKS_FIGURE = re.compile(r"\b(?:bang|tung|moi|kem|lan luot|la bao nhieu|bao nhieu|bao nhiu|bn|bnhiu|bnhieu|may|dem"
                          r"|so luong|tong so|so tien)\b")


def one_name_no_values(question: str, plan: QueryPlan) -> QueryPlan:
    """N80. The best-selling item by money within one product group, read as a one-row table (rank k = 1 with values;
    public run11, 6 questions, which the rankings refuse): a question that asks which one ("… nào … nhất") and no
    figure (no "bao nhiêu", "mấy", "bảng", "từng", "mỗi", "kèm") asks the name only. No train question asks a table of
    one row (every with_values in the verified bank has k 3 or 5 and "từng người")."""
    r = plan.rank
    if r is None or not r.with_values or r.k not in (1, None) or stated_k(question) is not None:
        return plan
    t = " ".join(tokens(question))
    # words that fold to a figure word: "máy" (a phone) as "mấy", "mới" as "mỗi", "bằng" as "bảng"; written with their
    # accents they ask no figure ("nhóm máy mới, … nhiều máy nhất")
    asks = " ".join(tokens(re.sub(r"(?i)\b(?:máy|mới|bằng)\b", " ", unicodedata.normalize("NFC", question))))
    if not (re.search(r"\bnao\b", t) and re.search(_SUPERLATIVE, t)) or _ASKS_FIGURE.search(asks):
        return plan
    if r.k is None and re.search(r"\b(?:cac|nhung|tat ca|liet ke)\b", t):
        return plan  # k left empty (every one) on a plural question: a list, not one name
    raw = plan.model_dump(mode="json", exclude_none=True)
    raw["rank"]["with_values"] = False
    raw["rank"]["k"] = 1  # "mặt hàng nào … nhiều máy nhất" written with k empty (public run11): one name
    raw.pop("answer_type", None)  # "table" was derived from with_values: derived again (a copy would keep it)
    return QueryPlan.model_validate(raw)


def k_not_the_month(question: str, plan: QueryPlan) -> QueryPlan:
    """N91. The customer with the most orders in a month, ranked with k = 5 (public run11 twice, the month written before its
    year read as a top 5): a k the question states nowhere but as the month of a "M-YYYY" / "M/YYYY" date is 1."""
    r = plan.rank
    if r is None or not r.k or r.k <= 1 or stated_k(question) is not None:
        return plan
    q = _plain(question)
    if not re.search(rf"(?<![\d/.])0?{r.k}\s*[-/]\s*(?:20)?\d\d\b", q) or re.search(rf"\btop\s*{r.k}\b", q):
        return plan
    raw = plan.model_dump(mode="json", exclude_none=True)
    raw["rank"]["k"] = 1
    raw.pop("answer_type", None)
    return QueryPlan.model_validate(raw)


_LISTED = re.compile(r"\b(?:th|thang|t)\s*(\d{1,2})((?:\s*(?:,|va|hay|hoac|voi)\s*(?:th|thang|t)?\s*\d{1,2})+)\s*/\s*(\d{4}|\d{2})\b")


def listed_months(question: str) -> list[str]:
    """Months a question lists with one year written once: "Th2, th3, th4/2026", "tháng 2, 3 và 4/2026" →
    2026-02, 2026-03, 2026-04. Empty when it lists none."""
    m = _LISTED.search(_plain(question).replace("và", "va"))
    if m is None:
        return []
    year = int(m.group(3)) if len(m.group(3)) == 4 else 2000 + int(m.group(3))
    months = [int(m.group(1))] + [int(x) for x in re.findall(r"\d{1,2}", m.group(2))]
    if not all(1 <= x <= 12 for x in months):
        return []
    return [f"{year:04d}-{x:02d}" for x in months]


def rank_months_as_listed(question: str, plan: QueryPlan) -> QueryPlan:
    """N97. Which of three listed months had the most revenue, ranked over the month of February alone (the
    LLM kept the one month written with its year): the months the question lists. A ranking of months over a single
    month is otherwise refused (asks=months): it can only answer that month."""
    r = plan.rank
    if r is None or r.entity != "month" or plan.period is None or plan.period.kind != "month":
        return plan
    months = listed_months(question) or [f"{y:04d}-{m:02d}" for m, y in stated_months(question)]
    months = sorted(set(months))
    if len(months) < 2:
        return plan
    return _rebuilt(plan, period={"kind": "months", "months": months})


_COUNTS_OBJECTS = r"\b(?:may|bao nhieu|bao nhiu|bn|bnhiu|bnhieu)\s+(?:mat hang|mon|san pham|sp|khach|nguoi|don|dh|ngay|xe|lo)\b"
_SELF_COUNTS = {("customer", "new_customer_count"), ("customer", "customer_count"), ("customer", "debtor_count")}


def threshold_as_value(question: str, plan: QueryPlan) -> QueryPlan:
    """N98. A count over a bound every object passes, read for a figure (units of one phone model sold this
    month read as the products with quantity ≥ 0; new member sign-ups read as the customers with new members
    ≥ 1, a metric that counts customers itself): the figure. Only when the question counts no objects for the first."""
    t = plan.threshold
    if plan.intent != "count_where" or t is None or t.as_share:
        return plan
    filters = [f.model_dump(mode="json", exclude_none=True) for m in plan.measures for f in m.filters]
    q = " ".join(tokens(denoised(question)))
    if (t.entity, t.metric) in _SELF_COUNTS and (t.op, t.value) in (("gte", 1), ("gt", 0)):
        return _rebuilt(plan, intent="value", threshold=None, measures=[{"metric": t.metric, "filters": filters}])
    if (t.op, t.value) == ("gte", 0) and not re.search(_COUNTS_OBJECTS, q):
        units = [m.unit for m in plan.measures if m.metric == t.metric and m.unit]
        measure = {"metric": t.metric, "filters": filters} | ({"unit": units[0]} if units else {})
        return _rebuilt(plan, intent="value", threshold=None, measures=[measure])
    return plan


_GROUP_NAMED = re.compile(r"\bnhom\s+([a-z0-9 ]+?)\s*(?:\?|\.|,|$|trong |thang |tuan |nam |quy )")


def orders_with_group(question: str, plan: QueryPlan) -> QueryPlan:
    """N98. Orders with at least one item of a product group, read as orders with at least one item, the group
    lost (public run11, 2 questions): the number of orders with an item of the group the question names (§1 "cả khi
    đếm số đơn có một mặt hàng"); the linking step checks the group is the shop's."""
    t = plan.threshold
    if plan.intent != "count_where" or t is None or t.entity != "order" or (t.op, t.value) not in (("gte", 1), ("gt", 0)):
        return plan
    if t.metric not in ("order_presence", "order_count", "quantity") or any(m.filters for m in plan.measures):
        return plan
    q = _plain(question)
    if re.search(_PERCENT, " ".join(tokens(q))):
        return plan
    m = _GROUP_NAMED.search(q + " ")
    if m is None or not m.group(1).strip():
        return plan
    words = re.findall(r"\w+", question.lower())
    folded = m.group(1).split()
    start = next((i for i in range(len(words)) if _plain(" ".join(words[i:i + len(folded)])) == m.group(1).strip()), None)
    value = " ".join(words[start:start + len(folded)]) if start is not None else m.group(1).strip()
    return _rebuilt(plan, intent="value", threshold=None,
                    measures=[{"metric": "order_count", "filters": [{"field": "product_group", "value": value}]}])


_MONTH_WORD = re.compile(r"^(?:t|th|thang)\s?\d{1,2}$")


def series_months_as_filters(question: str, plan: QueryPlan) -> QueryPlan:
    """N98. "Dthu <tháng>, <tháng>, <tháng> lần lượt mỗi tháng" read as one measure per month with the month as a category
    filter: one measure over the months the question lists (§2: a series of the months)."""
    if plan.intent != "series" or len(plan.measures) < 2:
        return plan
    def month_filters(m):
        return [f for f in m.filters if isinstance(f.value, str) and _MONTH_WORD.match(fold(f.value).strip())]
    if not all(len(month_filters(m)) == 1 for m in plan.measures):
        return plan
    rest = [[f for f in m.filters if f not in month_filters(m)] for m in plan.measures]
    if any(r != rest[0] for r in rest) or len({m.metric for m in plan.measures}) != 1:
        return plan
    months = listed_months(question)
    if len(months) != len(plan.measures):
        return plan
    base = plan.measures[0].model_dump(mode="json", exclude_none=True)
    base["filters"] = [f.model_dump(mode="json", exclude_none=True) for f in rest[0]]
    return _rebuilt(plan, measures=[base], period={"kind": "months", "months": months})


def stray_numeric_filters(question: str, plan: QueryPlan) -> QueryPlan:
    """N98. A debt age that is no number ("debt_age_days not_in missing" on "đếm các khách còn thiếu tiền"), or an
    expiry window of N days the question never writes beside the dates it does write ("lô còn tồn có hạn dùng từ
    <ngày> tới hết <ngày>" with expiry_within_days 365): dropped, the question's own words decide."""
    q = re.sub(r"[.,]", "", question)
    ages = re.search(r"\b(?:qua|tren|hon)\s+\d+\s*ngay\b|tuoi no", " ".join(tokens(question)))
    explicit = plan.period is not None and plan.period.kind == "range"

    def stray(f) -> bool:
        if f.field == "debt_age_days" and not ages:
            return not (isinstance(f.value, (int, float)) and not isinstance(f.value, bool))
        if f.field == "expiry_within_days" and explicit:
            try:
                return str(int(float(f.value))) not in q
            except (TypeError, ValueError):
                return True
        return False
    measures = [m.model_copy(update={"filters": [f for f in m.filters if not stray(f)]}) for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


_END_DAY = re.compile(r"\bden het(?: ngay)?\s+(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")


def lots_expiring_count(question: str, plan: QueryPlan, as_of: date | None) -> QueryPlan:
    """N99. "có mấy lô hàng còn tồn sẽ hết hạn từ nay đến hết ngày 22/09/2026", "bn lô chưa bán hết mà hạn dùng rơi vào
    120 ngày tới" (§6 Nhà thuốc "hàng hết hạn trong N ngày tới: lô còn tồn có hạn dùng từ D đến hết ngày D + N"), read
    as a stock, a list of unsold products…: the number of lots still holding goods with an expiry in that window.
    Train: the one such question, 5 lots, as the hand count of N74."""
    if as_of is None or plan.intent not in ("value", "list_items", "count_where"):
        return plan
    t = " ".join(tokens(denoised(question)))
    if not (re.search(r"\b(?:may|bao nhieu|bao nhiu|bn|bnhiu|bnhieu)\s+lo\b", t) and re.search(r"\b(?:han dung|het han|hsd)\b", t)):
        return plan
    spec = {"entity": "lot", "condition": "expiring_within", "count": True}
    days = re.search(r"\b(\d{1,4})\s*ngay\s*(?:toi|nua|sap toi)\b", t)
    end = _END_DAY.search(_plain(question))
    if days:
        spec["n"] = int(days.group(1))
        return _rebuilt(plan, intent="list_items", list_spec=spec, measures=[], threshold=None, period={"kind": "today"})
    if end:
        d = date(int(end.group(3)), int(end.group(2)), int(end.group(1)))
        if d < as_of:
            return plan
        return _rebuilt(plan, intent="list_items", list_spec=spec, measures=[], threshold=None,
                        period={"kind": "range", "start": as_of.isoformat(), "end": d.isoformat()})
    return plan


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
    """A count of repair tickets written as the orders with at least one order (or ticket) in them: every
    order, so the count of orders itself (public 06/11). Only that bound: ≥ 1 / > 0 on an order's own count."""
    t = plan.threshold
    if plan.intent != "count_where" or t is None or t.entity != "order" or t.as_share \
            or t.metric not in ("order_count", "ticket_count") or (t.op, t.value) not in (("gte", 1), ("gt", 0)):
        return plan
    filters = plan.measures[0].filters if plan.measures else []
    return QueryPlan.model_validate({"intent": "value", "period": plan.period.model_dump(exclude_none=True),
                                     "measures": [{"metric": t.metric, "filters": [f.model_dump() for f in filters]}]})


def unit_filter_as_unit(question: str, plan: QueryPlan) -> QueryPlan:
    """N76. A counting unit written as a filter ("quán bán dc bnhiu đĩa": revenue, filter unit = đĩa; "hqua bán đc mấy
    gói": order_count, filter unit = gói; run11 07/11, 4 such plans refused): the unit the measure counts in. A
    question with no money word then counts goods, so the measure is the quantity (§3). One unit filter, equal
    values only; a measure that already has another unit stays as it is."""
    t = " ".join(tokens(question))
    measures, changed = [], False
    for m in plan.measures:
        units = [f for f in m.filters if f.field == "unit"]
        values = {str(f.value).strip() for f in units if isinstance(f.value, str) and f.op == "eq"}
        if not units or len(values) != 1 or len(values) != len({str(f.value) for f in units}) \
                or (m.unit and m.unit.strip() not in values):
            measures.append(m)
            continue
        if re.search(_MONEY, t) or m.metric not in ("revenue", "order_count", "quantity"):
            measures.append(m)  # "doanh thu … bao nhiêu hỉ": a particle read as a unit beside a money word (run11)
            continue
        measures.append(m.model_copy(update={"metric": "quantity", "unit": values.pop(),
                                             "filters": [f for f in m.filters if f.field != "unit"]}))
        changed = True
    if not changed:
        return plan
    update = {"measures": measures}
    if plan.rank is not None and plan.rank.by in ("revenue", "order_count") and len(measures) == 1 \
            and measures[0].metric == "quantity":
        update["rank"] = plan.rank.model_copy(update={"by": "quantity"})
    return plan.model_copy(update=update)


_ORDER_WORDS = r"\b(?:dh|don|don hang|hoa don|bill|bil|order|o do)\b"


def orders_not_money(question: str, plan: QueryPlan) -> QueryPlan:
    """N76. Order counts asked in shorthand ("bnhiu đh") read as revenue (run11 07/11, refused by the
    measure gate): a question that counts orders ("đh", "đơn") and writes no money word asks the number of orders.
    One revenue measure, a value or a comparison, no unit."""
    t = " ".join(tokens(question))
    if plan.intent not in ("value", "compare", "series") or len(plan.measures) != 1:
        return plan
    m = plan.measures[0]
    if m.metric != "revenue" or m.unit or re.search(_MONEY, t) or re.search(_PERCENT, t) \
            or not re.search(_COUNTING + r"(?: \w+){0,2} " + _ORDER_WORDS, t):
        return plan
    kept = [f for f in m.filters if not (f.field == "order_status" and f.value == "completed")]
    return plan.model_copy(update={"measures": [m.model_copy(update={"metric": "order_count", "filters": kept})]})


_UNPAID = r"\b(?:chua gop|chua tra|con no|con thieu)\b"


def unpaid_as_debt(question: str, plan: QueryPlan) -> QueryPlan:
    """N80. §6 Điện thoại "phần góp chưa trả là tiền khách còn nợ": the money still unpaid on
    instalment contracts read as amount_due_total, what customers had to pay (public run11 and its retry, refused by the measure gate)
    asks the debt still owed, filters kept (the installment orders, one customer). Not when the question asks what the
    customer has to pay ("khách phải trả, gồm cả phần còn nợ" is amount_due_total, §6 Thu máy cũ). A value only."""
    if plan.intent != "value" or not any(m.metric == "amount_due_total" for m in plan.measures):
        return plan
    t = " ".join(tokens(question))
    if re.search(r"\bphai tra\b", t):
        return plan
    # "tiền chậm góp", "góp quá hạn": the overdue part only (§6 "kỳ góp có hạn trước ngày hỏi mà chưa góp đủ")
    to = "overdue_amount" if re.search(_OVERDUE, t) else "debt_total" if re.search(_UNPAID, t) else None
    if to is None:
        return plan
    raw = plan.model_dump(mode="json", exclude_none=True)
    for m in raw["measures"]:
        if m["metric"] == "amount_due_total":
            m["metric"] = to
    raw.pop("answer_type", None)
    return QueryPlan.model_validate(raw)


_OVERDUE = r"\b(?:cham gop|cham tra|qua han|tre han)\b"
_COUNTS_PEOPLE = r"\b(?:bao nhieu|bao nhiu|bnhiu|bnhieu|bn|may|mi|dem)\s+(?:khach|nguoi|ngui)\b"


def overdue_customers(question: str, plan: QueryPlan) -> QueryPlan:
    """N96. How many customers are late on instalments, read as a debt in money (one full public run 08/11, the run before had read
    it right): a question that counts customers and asks about overdue instalments, with no money word, asks the
    customers with an overdue instalment (§6 Điện thoại: "kỳ góp có hạn trước ngày hỏi mà chưa góp đủ là quá hạn").
    One debt measure, filters kept."""
    if plan.intent != "value" or len(plan.measures) != 1:
        return plan
    m = plan.measures[0]
    if m.metric not in {"debt_amount", "debt_total", "amount_due_total", "overdue_amount"}:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not (re.search(_COUNTS_PEOPLE, t) and re.search(_OVERDUE, t) and re.search(r"\bgop\b", t)) \
            or re.search(r"\btien\b", t):
        return plan
    raw = plan.model_dump(mode="json", exclude_none=True)
    raw["measures"][0]["metric"] = "overdue_installment_count"
    raw.pop("answer_type", None)
    return QueryPlan.model_validate(raw)


def _rebuilt(plan: QueryPlan, **changes) -> QueryPlan:
    """The plan with `changes` (top-level fields) and its answer type derived again."""
    raw = plan.model_dump(mode="json", exclude_none=True)
    raw.update(changes)
    raw.pop("answer_type", None)
    return QueryPlan.model_validate({k: v for k, v in raw.items() if v is not None})


def count_not_list(question: str, plan: QueryPlan) -> QueryPlan:
    """N85. How many items sold nothing in the last N days, read as the list (the count gate refused it,
    public run11 2 questions, both retries too): a question that counts and does not list asks how many."""
    ls = plan.list_spec
    if ls is None or ls.count:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not re.search(_COUNTING, t) or re.search(_LISTING, re.sub(_NONE_AT_ALL, " ", t)):
        return plan
    return _rebuilt(plan, list_spec=ls.model_copy(update={"count": True}).model_dump(mode="json", exclude_none=True))


def whole_as_share_of(plan: QueryPlan) -> QueryPlan:
    """N85. One diaper size as a percent of all diaper packs, written as a share of two measures, the part then its whole (the
    second's filters a strict part of the first's, same metric and unit), with no share_of (public run11; the share
    takes one measure): the second is the whole."""
    if plan.intent != "share" or plan.share_of is not None or len(plan.measures) != 2:
        return plan
    part, whole = plan.measures
    key = lambda m: {(f.field, f.op, str(f.value)) for f in m.filters}  # noqa: E731
    if part.metric != whole.metric or part.unit != whole.unit or not key(whole) < key(part):
        return plan
    return _rebuilt(plan, measures=[part.model_dump(mode="json", exclude_none=True)],
                    share_of=whole.model_dump(mode="json", exclude_none=True))


def share_as_value(question: str, plan: QueryPlan) -> QueryPlan:
    """N85. "Nhóm bánh kẹo <tháng> dthu nhiêu?" read as a share (refused: no percent word): one measure, no
    whole, a question with no percent word asks the figure itself."""
    if plan.intent != "share" or plan.share_of is not None or len(plan.measures) != 1:
        return plan
    if re.search(_PERCENT, " ".join(tokens(denoised(question)))):
        return plan
    return _rebuilt(plan, intent="value")


_TIME_ENTITY = {"thang": "month", "ngay": "day"}


def which_time_as_rank(question: str, plan: QueryPlan) -> QueryPlan:
    """N85. Which month of a three-month span had the highest revenue, read as the series of the
    months (refused, asks=which_time): the month (day) ranked first by that figure over the period. Highest only: the
    rankings refuse ascending order."""
    if plan.intent not in ("series", "value") or len(plan.measures) != 1 or plan.period is None:
        return plan
    t = " ".join(tokens(denoised(question)))
    m = re.search(r"\b(thang|ngay) nao\b", t)
    if m is None or not re.search(r"\b(?:cao|nhieu|lon) (?:nhat|nhut)\b", t) or re.search(r"\b(?:thap|it) nhat\b", t):
        return plan
    measure = plan.measures[0]
    return _rebuilt(plan, intent="rank",
                    rank={"entity": _TIME_ENTITY[m.group(1)], "by": measure.metric, "k": 1},
                    measures=[measure.model_dump(mode="json", exclude_none=True)])


def rulebook_rank_terms(question: str, plan: QueryPlan) -> QueryPlan:
    """N85. Ranking terms the rulebook defines, read with another criterion (public run11, refused by the measure
    gate): §5 "nhà cung cấp chính" is the one with the most receipts (read as the most money bought); §3 "khách sộp
    nhất" the highest average order among customers with 3 orders or more (read as revenue)."""
    t = " ".join(tokens(denoised(question)))
    if re.search(r"\b(?:nha cung cap|ncc) chinh\b", t) and (
            (plan.rank is not None and plan.rank.entity == "supplier")
            or any(m.metric == "purchase_amount" for m in plan.measures)) and not any(m.filters for m in plan.measures):
        if plan.rank is None or plan.rank.by != "receipt_count":
            return _rebuilt(plan, intent="rank", rank={"entity": "supplier", "by": "receipt_count", "k": 1},
                            measures=[])
    r = plan.rank
    if r is not None and r.entity == "customer" and re.search(r"\bsop\b", t) and r.by != "avg_order_value" \
            and not any(m.filters for m in plan.measures):
        return _rebuilt(plan, rank={"entity": "customer", "by": "avg_order_value", "k": r.k, "min_orders": 3},
                        measures=[])
    # N109. §3 "Ngày đắt khách nhất: ngày có nhiều đơn nhất trong kỳ" (the busiest day of a
    # month, ranked by customers, which no day ranking counts: public run11, no figure)
    if r is not None and r.entity == "day" and re.search(r"\bdat khach (?:nhat|nhut)\b", t) and r.by != "order_count" \
            and not any(m.filters for m in plan.measures):
        return _rebuilt(plan, rank={"entity": "day", "by": "order_count", "k": r.k, "order": r.order}, measures=[])
    # N138. §3 "Bán chạy: theo số lượng … Bán nhiều nhất, bán được nhiều nhất, hot nhất cùng nghĩa với bán chạy nhất":
    # "cho tôi 3 món hot nhất tháng 3" ranked by revenue (train, refused by the measure gate, the retry too)
    if r is not None and r.entity == "product" and r.by == "revenue" and re.search(_BEST_SELLING, t) \
            and not re.search(_MONEY, t) and not any(m.filters for m in plan.measures):
        return _rebuilt(plan, rank={**r.model_dump(mode="json", exclude_none=True), "by": "quantity"}, measures=[])
    return plan


_BEST_SELLING = r"\b(?:ban chay|hot|best|ban nhieu|ban duoc nhieu)\b"


# N137, N139–N142 (09/11): train questions with no plan at all, read wrong on the first call and the retry alike, in
# a way the rulebook settles. Each rewrites the misread part instead of refusing the plan; the rewritten plan meets
# every gate as any other.

_QUARTER_WRITTEN = re.compile(r"\b(?:quy|q) ([1-4]) (?:nam )?(20\d\d)\b")


def quarter_written(question: str, plan: QueryPlan) -> QueryPlan:
    """N137. §2 "quý Q … mỗi quý 3 tháng tính từ tháng 1": "số đơn quý 2/2025", "số đơn quý 1/2026" read as February
    2025, January 2026 (train 2 questions, refused kind=month, the retries too): a question that writes one quarter
    with its year, and a plan whose one period is the month of that number in that year, asks the quarter."""
    t = " ".join(tokens(denoised(question)))
    found = set(_QUARTER_WRITTEN.findall(t))
    p = plan.period
    if len(found) != 1 or p is None or p.kind != "month" or plan.compare is not None:
        return plan
    q, y = (int(x) for x in found.pop())
    if p.month != q or p.year not in (None, y):
        return plan
    return _rebuilt(plan, period={"kind": "quarter", "year": y, "quarter": q})


_ORDERS_COUNTED = r"\bso (?:luong )?(?:dh|don|don hang|hoa don|bil|bill|order)\b"
_ORDER_NOUN = frozenset({"so", "luong", "dh", "don", "hang", "hoa", "bil", "bill", "order"})


def orders_counted(question: str, plan: QueryPlan) -> QueryPlan:
    """N140. "số bill quý 2/2026 là bnhiu", "số đơn ca chiều tăng hay giảm bao nhiêu % so với ca sáng" read as revenue
    (train 2 questions, refused metric=revenue, the retries too; orders_not_money leaves a percent alone): a question
    that names the number of orders ("số đơn", "số bill", §3) and no money word asks the orders, also as a percent.
    Filters whose value is only those words ("payment_method = số bill") go; others stay."""
    t = " ".join(tokens(denoised(question)))
    if not re.search(_ORDERS_COUNTED, t) or re.search(_MONEY, t) or not plan.measures:
        return plan
    if plan.intent not in ("value", "compare", "series", "trend") or any(
            m.metric != "revenue" or m.unit for m in plan.measures):
        return plan

    def noun_only(v) -> bool:
        return set(tokens(denoised(str(v)))) <= _ORDER_NOUN

    def fix(m):
        kept = [f for f in m.filters if not (f.field == "order_status" and f.value == "completed")
                and not (isinstance(f.value, str) and noun_only(f.value))]
        return m.model_copy(update={"metric": "order_count", "filters": kept})
    return plan.model_copy(update={"measures": [fix(m) for m in plan.measures]})


def warranty_not_asked(question: str, plan: QueryPlan) -> QueryPlan:
    """N141. A warranty flag on a question that never says "bảo hành" ("doanh thu tháng sau có luôn cao hơn tháng
    trước", "dthu tháng 2/2026 so với cùng kỳ năm ngoái": train 4 questions in 3 shops, none of them §6 phone or repair
    shops; the flag comes from the examples, not from the question). The filter gate refuses exactly these; the flag is
    dropped instead, every other part kept."""
    if re.search(r"\b(?:bao hanh|bh)\b", fold(question)):
        return plan

    def fix(m):
        if m.metric not in _SALES:  # a repair shop's tickets: "phiếu sửa xe" may well mean not warranty, refused
            return m
        kept = [f for f in m.filters if f.field != "is_warranty"]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) for m in plan.measures]
    if measures == list(plan.measures):
        return plan
    # measures told apart by the flag alone (warranty false / true) are one measure once it goes: a same-period
    # comparison written as two revenues, flag false and true, would otherwise keep two equal measures
    seen, kept = set(), []
    for m in measures:
        key = m.model_dump_json()
        if key not in seen:
            seen.add(key)
            kept.append(m)
    return _rebuilt(plan, measures=[m.model_dump(mode="json", exclude_none=True) for m in kept])  # answer type again


_AMOUNTS_ASKED = r"\b(?:bao nhieu|bao nhiu|bn|bnhiu|so tien|so no|kem|bang|moi nguoi|tung nguoi|tung khach|moi khach)\b"


def debtors_ranked(question: str, plan: QueryPlan) -> QueryPlan:
    """N142. §4 "3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu" read as one debt with the filter
    "customer = top_3", or as a ranking with the typo "nowj" as a customer (train 2 questions, refused, the retries too):
    a question that states k customers (k ≥ 2) and the most debt, and a plan on debt_amount, asks the customers ranked
    by debt, with their amounts when the question asks them."""
    t = " ".join(tokens(denoised(question)))
    k = stated_k(question)
    if k is None or k < 2 or not re.search(r"\bkhach\b", t) or not re.search(r"\bno\b", t) \
            or not re.search(_SUPERLATIVE, t):
        return plan
    metrics = [m.metric for m in plan.measures] + ([plan.rank.by] if plan.rank else [])
    if "debt_amount" not in metrics or any(m != "debt_amount" for m in metrics):
        return plan
    r = plan.rank
    if r is not None and r.entity == "customer" and r.k == k and not any(m.filters for m in plan.measures):
        return plan
    return _rebuilt(plan, intent="rank", measures=[], compare=None, threshold=None,
                    rank={"entity": "customer", "by": "debt_amount", "k": k,
                          "with_values": bool(re.search(_AMOUNTS_ASKED, t))})


def gross_profit_named(question: str, plan: QueryPlan) -> QueryPlan:
    """N139. §5 "Lãi gộp": "tháng 8/2025 lãi gộp của cửa hàng là bao nhiêu" read as revenue with a filter
    "product_group = lai gop" (train, refused metric=revenue, the retry too): a question that names the gross profit
    asks it; filters whose value is that name go."""
    t = " ".join(tokens(denoised(question)))
    if not re.search(r"\b(?:lai gop|loi nhuan gop|lai gross)\b", t) or plan.intent not in ("value", "compare", "series") \
            or len(plan.measures) != 1 or plan.measures[0].metric != "revenue":
        return plan
    m = plan.measures[0]
    kept = [f for f in m.filters if not (isinstance(f.value, str) and fold(f.value) in ("lai gop", "loi nhuan gop"))]
    return plan.model_copy(update={"measures": [m.model_copy(update={"metric": "gross_profit", "filters": kept})]})


_IN_MINUS_OUT = re.compile(r"\bnhap\b(?: \w+){0,6} (?:tru|chenh)\b(?: \w+){0,5} ban\b"
                           r"|\bchenh(?: lech)?\b(?: \w+){0,3} nhap\b(?: \w+){0,3} ban\b")


_COUNTED_UNITS = frozenset({"lon", "chai", "ly", "coc", "thung", "goi", "hop", "bich", "vi", "vien", "tuyp", "kg",
                            "lit", "dia", "to", "phan", "cay", "ket", "tui", "binh", "hu", "lo", "cai", "chiec", "bo",
                            "cuon", "met", "bao", "tam", "mieng", "ong", "can"})


def in_minus_out(question: str, plan: QueryPlan) -> QueryPlan:
    """N86. §5 "nhập trừ bán, chênh nhập và bán" (units bought in minus units sold) read
    as the stock, the money bought or two figures (public run11 4 questions, train 2; refused by the measure gates):
    the one figure purchase_minus_sales of the product the plan names, in the unit it names."""
    if plan.intent != "value" or not plan.measures:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not _IN_MINUS_OUT.search(t) or re.search(_MONEY, t):  # §5 counts quantities: "tiền nhập trừ tiền bán" is not it
        return plan
    if [m.metric for m in plan.measures] == ["purchase_minus_sales"]:
        return plan
    named = next((m for m in plan.measures if any(f.field == "product" for f in m.filters)), None)
    if named is None:
        return plan
    unit = next((m.unit for m in plan.measures if m.unit), None)
    if unit is None:  # "… là bao nhiêu viên": the unit after the counting word (compared folded, stock._same_unit)
        t = " ".join(tokens(denoised(question)))  # also packs or tablets bought in minus sold
        unit = next((w for w in re.findall(r"\b(?:bao nhieu|bao nhiu|bn|bnhiu|bnhieu|may|tong|so|dem) (\w+)", t)
                     if w in _COUNTED_UNITS), None)
    measure = {"metric": "purchase_minus_sales",
               "filters": [f.model_dump(mode="json", exclude_none=True) for f in named.filters if f.field == "product"]}
    if unit:
        measure["unit"] = unit
    return _rebuilt(plan, measures=[measure])


def weekday_as_stated(question: str, plan: QueryPlan) -> QueryPlan:
    """N85. "các ngày thứ 3 tháng này" planned with weekday = wed (public run11; refused, the filter has no ground): when
    the question names exactly one weekday and the plan filters on one other, the one the question names."""
    q = fold(question)
    stated = [v for v, pats in VALUE_TRIGGERS["weekday"].items() if any(re.search(rf"\b{p}\b", q) for p in pats)]
    if len(stated) != 1:
        return plan

    def fix(m):
        fs = [f.model_copy(update={"value": stated[0]}) if f.field == "weekday" and f.op == "eq"
              and isinstance(f.value, str) and f.value != stated[0] else f for f in m.filters]
        return m.model_copy(update={"filters": fs}) if fs != list(m.filters) else m
    days = {f.value for m in plan.measures for f in m.filters if f.field == "weekday"}
    if len(days) != 1:
        return plan
    measures = [fix(m) for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


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


def debt_age_from_question(question: str, plan: QueryPlan) -> QueryPlan:
    """N87. "khách còn nợ ở các đơn đã đặt quá 7 ngày" planned with debt_age_days "gt" whose value is a word ("gt", the
    N in a note or nowhere; public run11 5 questions, train 1): the age the question states, when it states exactly
    one ("quá / hơn / trên N ngày": older than N days, §4 "tuổi nợ: số ngày tính từ ngày đặt"). N164: also the same N
    written "gte" ("các đơn đặt đã hơn 7 ngày" as age ≥ 7: train 2 questions, the answers are the orders older than 7
    days; with ≥ one of them counts the 7-day-old orders too)."""
    ages_written = [f for m in plan.measures for f in m.filters if f.field == "debt_age_days"]
    ages = set(re.findall(r"\b(?:qua|tren|hon)\s+(\d+)\s*ngay\b", " ".join(tokens(denoised(question)))))
    if len(ages_written) != 1 or len(ages) != 1:
        return plan
    f = ages_written[0]
    numeric = isinstance(f.value, (int, float)) and not isinstance(f.value, bool)
    n = float(next(iter(ages)))
    if numeric and not (f.op == "gte" and float(f.value) == n):
        return plan
    raw = plan.model_dump(mode="json", exclude_none=True)
    for m in raw["measures"]:
        m["filters"] = [{"field": "debt_age_days", "op": "gt", "value": n} if f["field"] == "debt_age_days" else f
                        for f in m.get("filters", [])]
    raw.pop("answer_type", None)
    return QueryPlan.model_validate(raw)


def debt_age_added(question: str, plan: QueryPlan) -> QueryPlan:
    """N174. "những đơn đặt cách đó hơn 15 ngày mà chưa trả hết còn nợ tổng cộng bn", "các đơn đặt đã hơn 15 ngày mà
    khách chưa trả hết còn nợ bao nhiêu" read as the whole debt with an order status ("completed") or a payment method
    ("credit") for "chưa trả hết", no age (train 2, both refused: asks=debt_age). One debt measure, the question stating
    exactly one age of orders: the debt of the orders older than that (§4 tuổi nợ; the verified plans of the template
    have that age filter and no other); "chưa trả hết" restates the debt, its status and payment filters go."""
    t = " ".join(tokens(denoised(question)))
    ages = set(re.findall(r"\b(?:qua|tren|hon|lau hon)\s+(\d+)\s*ngay\b", t))
    if plan.intent != "value" or len(plan.measures) != 1 or len(ages) != 1 or not re.search(r"\bdon\b", t):
        return plan
    m = plan.measures[0]
    if m.metric not in ("debt_total", "debt_amount") or any(f.field == "debt_age_days" for f in m.filters):
        return plan
    kept = [f.model_dump(mode="json", exclude_none=True) for f in m.filters
            if f.field not in ("order_status", "payment_method")]
    age = {"field": "debt_age_days", "op": "gt", "value": float(next(iter(ages)))}
    measure = {**m.model_dump(mode="json", exclude_none=True), "filters": kept + [age], "unit_split": False}
    return _rebuilt(plan, measures=[measure])


def split_debt_ages(plan: QueryPlan) -> QueryPlan:
    """Debt left split into age bands of days (train 5 questions, answered as a list; public 06/11
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
    """"Từ hồi <món> lên giá <giá>, so 30 ngày kể từ ngày đổi giá…" names the day by the new price, not by a
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


_AVERAGE = r"\b(?:trung binh|binh quan|tb)\b"
_PER_ORDER = r"\b(?:moi|mot|1) (?:don|dh|hoa don)\b"
_DUE_READINGS = {"avg_order_value", "amount_due_total", "trade_in_amount"}


def due_per_order(question: str, plan: QueryPlan) -> QueryPlan:
    """N101. §6 Điện thoại: the average a customer pays per order after discount and trade-in, read
    as avg_order_value (the revenue: refused, §6 "khách phải trả" is after the discount and the trade-in), or as the
    amount due beside the trade-in and the average (public run11, 3 questions, every retry refused): the amount due
    over the period's orders, per order (internal metric avg_amount_due). The filters the question grounds and every
    measure shares are kept."""
    if plan.intent != "value" or plan.rank is not None or plan.compare is not None or plan.list_spec is not None:
        return plan
    metrics = {m.metric for m in plan.measures}
    if not metrics & {"avg_order_value", "amount_due_total"} or not metrics <= _DUE_READINGS:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not (re.search(r"\bphai tra\b", t) and re.search(_AVERAGE, t) and re.search(_PER_ORDER, t)):
        return plan
    bad = set(ungrounded_filters(question, plan))
    key = lambda f: (f.field, f.op, str(f.value))  # noqa: E731
    shared = [f for f in plan.measures[0].filters if f"{f.field}={f.value}" not in bad
              and all(key(f) in {key(g) for g in m.filters} for m in plan.measures)]
    return _rebuilt(plan, measures=[{"metric": "avg_amount_due",
                                     "filters": [f.model_dump(mode="json", exclude_none=True) for f in shared]}])


_TOGETHER = r"\b(?:gop|gom|cong|tinh|ke|tat) ca\b|\bca \w+(?: \w+)? (?:lan|voi|va) \w+"
_APART = r"\b(?:lan luot|lan nuot|tung|rieng|tach|moi (?:ben|loai|nhom|kenh|cai|thu))\b"
_NAME_FIELDS = ("category", "product_group", "product", "product_line", "brand", "channel", "payment_method")


def values_together(question: str, plan: QueryPlan) -> QueryPlan:
    """N101. Phones sold in a month counting new and used together, read as two values of one field on
    one measure (both at once: no line is both, 0), or as one measure per value (two numbers; public run11, 2
    questions): a question that puts the values together ("gộp cả", "tính cả X lẫn Y", "tất cả") and does not ask
    them apart ("lần lượt", "từng", "riêng") asks one figure over any of them (op "in"). Values the question writes."""
    if plan.intent != "value" or plan.rank is not None or plan.compare is not None or plan.list_spec is not None:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not re.search(_TOGETHER, t) or re.search(_APART, t):
        return plan
    q = fold(question)

    def written(values) -> bool:
        return len(values) >= 2 and len({fold(str(v)) for v in values}) == len(values) and all(
            isinstance(v, str) and fold(v) in q for v in values)

    def merged(filters, field, values) -> list[dict]:
        rest = [f.model_dump(mode="json", exclude_none=True) for f in filters if f.field != field]
        return rest + [{"field": field, "op": "in", "value": list(values)}]

    if len(plan.measures) == 1:
        m = plan.measures[0]
        for field in _NAME_FIELDS:
            same = [f for f in m.filters if f.field == field]
            values = [f.value for f in same]
            if len(same) >= 2 and all(f.op == "eq" for f in same) and written(values):
                raw = m.model_dump(mode="json", exclude_none=True)
                raw["filters"] = merged(m.filters, field, values)
                return _rebuilt(plan, measures=[raw])
        return plan
    first = plan.measures[0]
    if any((m.metric, m.aggregate, m.unit, m.unit_split) != (first.metric, first.aggregate, first.unit,
                                                             first.unit_split) for m in plan.measures):
        return plan
    for field in _NAME_FIELDS:
        own = [[f for f in m.filters if f.field == field] for m in plan.measures]
        rest = [{(f.field, f.op, str(f.value)) for f in m.filters if f.field != field} for m in plan.measures]
        if all(len(o) == 1 and o[0].op == "eq" for o in own) and all(r == rest[0] for r in rest) \
                and written([o[0].value for o in own]):
            raw = first.model_dump(mode="json", exclude_none=True)
            raw["filters"] = merged(first.filters, field, [o[0].value for o in own])
            return _rebuilt(plan, measures=[raw])
    return plan


_TRADE_IN = r"\bthu(?: lai)? may cu\b"


def trade_in_share(question: str, plan: QueryPlan) -> QueryPlan:
    """N101. §6 Điện thoại: the percent of a month's orders that took a used phone in
    read as the trade-in total (refused: a percent), or as a share of warranty orders, of a category "trade_in" (public
    run11, 2 questions, every retry refused): the orders with a trade-in over every order of the period, both neither
    cancelled nor returned (§1, §6 "chỉ tính đơn không huỷ, không trả"); internal metric trade_in_order_count."""
    metrics = {m.metric for m in plan.measures} | ({plan.share_of.metric} if plan.share_of else set())
    if plan.intent not in ("value", "share") or plan.rank is not None or plan.compare is not None \
            or plan.list_spec is not None or not metrics <= {"order_count", "trade_in_amount"}:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not (re.search(_TRADE_IN, t) and re.search(_PERCENT, question.lower() + " " + t)
            and re.search(r"\b(?:don|dh|don hang|hoa don)\b", t)):
        return plan
    return _rebuilt(plan, intent="share", measures=[{"metric": "trade_in_order_count", "filters": []}],
                    share_of={"metric": "order_count", "filters": []})


_PHONES_MONEY = r"\b(?:tien ban may|dthu may|doanh thu may|doanh so may)\b"


def phones_as_whole(question: str, plan: QueryPlan) -> QueryPlan:
    """N102. §6 Điện thoại: new phones as a percent of phone revenue (accessories
    left out) read with the shop's whole revenue as the whole, or with the part and accessories as a
    second measure (public run11, 2 questions refused by the share_of=phones gate, every retry too): the whole is the
    part's metric over the phones (category "máy": the linking reads it as every kind that is no accessory, N102)."""
    if plan.intent != "share" or not plan.measures or (plan.share_of is not None and plan.share_of.filters):
        return plan
    part = plan.measures[0]
    if not any(f.field == "category" for f in part.filters):
        return plan
    if not re.search(_PHONES_MONEY, " ".join(tokens(denoised(question)))):
        return plan
    return _rebuilt(plan, measures=[part.model_dump(mode="json", exclude_none=True)],
                    share_of={"metric": part.metric, "filters": [{"field": "category", "value": "máy"}]})


def warranty_over_sold(question: str, plan: QueryPlan) -> QueryPlan:
    """N102. §6 Điện thoại "Tỉ lệ bảo hành của một quý bằng số lượt bảo hành có ngày nhận trong quý, chia cho số máy
    bán trong quý": a quarter's warranty visits as a percent of phones sold, read as the two figures, each
    with order_status = completed (public run11, both readings): the rate."""
    if plan.intent != "value" or len(plan.measures) != 2 \
            or {m.metric for m in plan.measures} != {"warranty_count", "quantity"} \
            or any(f.field != "order_status" for m in plan.measures for f in m.filters):
        return plan
    t = " ".join(tokens(denoised(question)))
    if not (re.search(_PERCENT, question.lower() + " " + t) and re.search(r"\bbao hanh\b", t)):
        return plan
    return _rebuilt(plan, measures=[{"metric": "warranty_rate", "filters": []}])


_T_MONTH = re.compile(r"\bt\s?(\d{1,2})\s*[/-]\s*(\d{4}|\d{2})\b")


def month_written_as_t(question: str, plan: QueryPlan) -> QueryPlan:
    """N102. "Tổng dthu <tháng> đc bnhiu?" ("T1" = tháng 1) read as quarter 1 (public run11; the template reading
    said month 1, so the two disagreed and nothing was answered): a quarter the question never names ("quý", "Q1")
    where it writes "T<m>/<year>" is that month."""
    p = plan.period
    if p is None or p.kind != "quarter":
        return plan
    if re.search(r"\b(?:quy|qui)\b|\bq\s?\d", fold(question)) or re.search(r"\bq\s?\d", question.lower()):
        return plan
    m = _T_MONTH.search(question.lower())
    if m is None:
        return plan
    month, year = int(m.group(1)), int(m.group(2))
    year = year + 2000 if year < 100 else year
    if not 1 <= month <= 12 or (p.year is not None and p.year != year):
        return plan
    return _rebuilt(plan, period={"kind": "month", "year": year, "month": month})


# N103. Sentence-final particles ("Doanh thu <tháng> quán được bao nhiêu hỉ?") the reader wrote as a counting unit
# beside a money word (public run11; unit_filter_as_unit leaves those, N76): no shop counts in them
_PARTICLES = {"hi", "nhi", "ha", "hen", "nha", "nhe", "a", "z", "vay", "oi", "do", "day", "the", "nho", "ta"}


def particle_not_unit(plan: QueryPlan) -> QueryPlan:
    def fix(m):
        kept = [f for f in m.filters if not (f.field == "unit" and f.op == "eq" and isinstance(f.value, str)
                                             and fold(f.value).strip() in _PARTICLES)]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


_TODAY = r"\b(?:hom nay|hnay|bua nay|bua ni|hom ni)\b"
_MONTH_NAMED = r"\b(?:thang|th)\b"


def today_not_this_month(question: str, plan: QueryPlan) -> QueryPlan:
    """N103. "Hom nay ban duoc may don?" read as this month (public run11; the template reading said today, so the
    two disagreed and nothing was answered): a question that says today and names no month asks today (§2 "Ngày X,
    hôm nay, hôm qua: chỉ trong ngày đó")."""
    if plan.period is None or plan.period.kind != "this_month" or plan.compare is not None:
        return plan
    t = " ".join(tokens(denoised(question)))
    if not re.search(_TODAY, t) or re.search(_MONTH_NAMED, t):
        return plan
    return _rebuilt(plan, period={"kind": "today"})


# N103. §6 Mẹ và bé "phí giao", "trừ điểm": a month's shipping fees (typed without accents) read as the revenue of the
# orders paid "Ship", the points customers used as the revenue of a customer "dùng điểm"
# (public run11, 2 questions, no value linked): the order amount the words name, the restating filter dropped
_ORDER_AMOUNT_WORDS = (("shipping_fee_total", r"\b(?:phi|tien) (?:ship|giao hang|giao|van chuyen)\b", r"ship|giao"),
                       ("points_discount", r"\b(?:dung|tru|doi) diem\b|\bdiem tich luy\b", r"diem"),
                       # N110: "vâu chơ" as said aloud (a full public run 08/11 read it as revenue under is_warranty)
                       ("voucher_discount", r"\bvoucher\b|\bvau cho\b|\bma giam gia\b", r"voucher|vau cho|giam gia"))


# N120. "bán được mấy đĩa cơm chiên dương châu" read as revenue: "bán được" is a word of revenue too, so the measures
# gate let it pass (train, a re-read of 08/11: answered 20 615 000 for 299 plates). A question that counts in a unit
# and names no money is a quantity in that unit (§3 "bán được bao nhiêu <đơn vị>").
_COUNT_UNIT = re.compile(r"\b(?:may|bao nhieu|bao nhiu|bnhiu|bnhieu|bn)\s+(ly|coc|dia|lon|chai|goi|hop|cai|bich|thung|"
                         r"kg|cay|vien|phan|to|suat|cuon|tam|met|lit|vi|tuyp|lo|mieng|chiec|bo|bao|ket|loc|xuat)\b")
_MONEY_NAMED = re.compile(r"\b(?:doanh thu|doanhthu|dthu|dt|revenue|tien|dong|vnd|thu ve|thu duoc|bac|trieu|tr|k|nghin|"
                          r"ngan|cu)\b")
_UNIT_SPELLING = {"ly": "ly", "coc": "cốc", "dia": "đĩa", "lon": "lon", "chai": "chai", "goi": "gói", "hop": "hộp",
                  "cai": "cái", "bich": "bịch", "thung": "thùng", "kg": "kg", "cay": "cây", "vien": "viên",
                  "phan": "phần", "to": "tô", "suat": "suất", "cuon": "cuộn", "tam": "tấm", "met": "mét", "lit": "lít",
                  "vi": "vỉ", "tuyp": "tuýp", "lo": "lọ", "mieng": "miếng", "chiec": "chiếc", "bo": "bộ", "bao": "bao",
                  "ket": "két", "loc": "lốc", "xuat": "xuất"}


def quantity_not_money(question: str, plan: QueryPlan) -> QueryPlan:
    if plan.intent != "value" or len(plan.measures) != 1 or plan.measures[0].metric != "revenue":
        return plan
    t = " ".join(tokens(question))
    m = _COUNT_UNIT.search(t)
    if m is None or _MONEY_NAMED.search(t):
        return plan
    measure = plan.measures[0].model_dump(mode="json", exclude_none=True)
    measure.update({"metric": "quantity", "unit": _UNIT_SPELLING[m.group(1)]})
    return _rebuilt(plan, measures=[measure])


def order_amount_named(question: str, plan: QueryPlan) -> QueryPlan:
    """N103 / N110. The order amount the question names (fee, points, voucher) read as revenue under a filter: the
    amount, the filter that restates it dropped. N110: also when no filter restates the words but every filter has no
    ground in the question (a voucher discount total typed with typos, read as revenue with is_warranty = true)."""
    if plan.intent != "value" or len(plan.measures) != 1 or plan.measures[0].metric != "revenue":
        return plan
    m = plan.measures[0]
    t = " ".join(tokens(denoised(question)))
    for metric, asks, restates in _ORDER_AMOUNT_WORDS:
        if not re.search(asks, t):
            continue
        said = [f for f in m.filters if isinstance(f.value, str) and re.search(restates, fold(f.value))]
        bad = set(ungrounded_filters(question, plan))  # "tiem thu phi ship": the shop, not a channel "Tại tiệm"
        if not said and m.filters and all(f"{f.field}={f.value}" in bad for f in m.filters):
            return _rebuilt(plan, measures=[{"metric": metric, "filters": []}])
        if len(said) != 1:
            return plan
        kept = [f.model_dump(mode="json", exclude_none=True) for f in m.filters
                if f is not said[0] and f"{f.field}={f.value}" not in bad]
        return _rebuilt(plan, measures=[{"metric": metric, "filters": kept}])
    return plan


# N110. Amounts of a whole order (what the customer pays, the trade-in, a voucher, points, the shipping fee) are not
# split by item: an item filter on them that the question does not write is no reading of it (what customers paid
# after the discount and the trade-in, read with category = "trả góp", the retry "mua
# chịu": a full public run 08/11, no figure). Dropped instead of refusing the plan, only when the value is a way of
# paying or selling (a payment / channel code of synonyms.json, "mua chịu", "nợ"), never an item: an item the question
# writes short ("ip 15") may fail the ground test, and the shop's total would then be a wrong answer, not a blank.
_ORDER_LEVEL = frozenset({"amount_due_total", "avg_amount_due", "trade_in_amount", "voucher_discount",
                          "points_discount", "shipping_fee_total"})
_ITEM_FIELDS = ("category", "product_group", "product", "product_line", "brand")


def _payment_term(value) -> bool:
    if not isinstance(value, str):
        return False
    from . import linking  # late import, as in _coded_grounded
    return (linking.concept("payment_method", value) is not None or linking.concept("channel", value) is not None
            or bool(_DEBT_WORDS.match(fold(value).strip())))


def order_amount_no_item(question: str, plan: QueryPlan) -> QueryPlan:
    if not any(m.metric in _ORDER_LEVEL and any(f.field in _ITEM_FIELDS for f in m.filters) for m in plan.measures):
        return plan
    bad = set(ungrounded_filters(question, plan))

    def fix(m):
        if m.metric not in _ORDER_LEVEL:
            return m
        kept = [f for f in m.filters if not (f.field in _ITEM_FIELDS and f.op == "eq" and _payment_term(f.value)
                                             and f"{f.field}={f.value}" in bad)]
        return m.model_copy(update={"filters": kept}) if len(kept) < len(m.filters) else m
    measures = [fix(m) for m in plan.measures]
    return plan.model_copy(update={"measures": measures}) if measures != list(plan.measures) else plan


# N110. "Cất hàng" is to buy goods in for the shop (nhập hàng), as the South and Centre say it: "tháng 8/2026 quán cất
# hàng hết bao nhiêu tiền" read as the stock's value at the end of August on a full public run 08/11 (no figure: the
# shop keeps no stock count). Only when the question says nothing of stock left ("tồn", "còn").
_STOCKED_IN = r"\bcat hang\b"
_STOCK_LEFT = r"\b(?:ton|con)\b"


def stocked_in_as_purchase(question: str, plan: QueryPlan) -> QueryPlan:
    if not any(m.metric in ("stock_value", "stock_qty") for m in plan.measures):
        return plan
    t = " ".join(tokens(denoised(question)))
    if not re.search(_STOCKED_IN, t) or re.search(_STOCK_LEFT, t):
        return plan
    if any(m.metric == "stock_qty" for m in plan.measures) and not re.search(r"\b(?:tien|gia tri)\b", t):
        return plan  # a count of goods bought in: no metric counts it
    measures = [m.model_copy(update={"metric": "purchase_amount", "unit": None, "unit_split": False})
                if m.metric in ("stock_value", "stock_qty") else m for m in plan.measures]
    return plan.model_copy(update={"measures": measures})


_AVERAGE_WORDS = re.compile(r"\b(?:trung binh|tb|binh quan|moi ngay|mot ngay|1 ngay|bq)\b")


def average_not_asked(question: str, plan: QueryPlan) -> QueryPlan:
    """N165. An average per day the question never asks for (cups of one drink in the 30 days
    after a price rise against the 30 days before, the change in plates sold in percent) read with aggregate avg_per_day; train
    2 questions, refused for a rule the train rulebook does not have): the totals the question asks. Only on a
    comparison of two windows of the same length, where the two readings give the same percentage."""
    if plan.compare is None or plan.compare.kind != "before_days_from" or plan.period is None \
            or plan.period.kind != "days_from" or not any(m.aggregate != "total" for m in plan.measures):
        return plan
    if _AVERAGE_WORDS.search(" ".join(tokens(denoised(question)))):
        return plan
    measures = [{**m.model_dump(mode="json", exclude_none=True), "aggregate": "total"} for m in plan.measures]
    return _rebuilt(plan, measures=measures)


_MONTH_NOTE = re.compile(r"^(?:t|th|thg|thang)?\s*\d{1,2}\s*(?:/|-|\.|\s)\s*(?:nam\s*)?\d{2,4}$|^nam\s*\d{4}$")


def month_note_dropped(plan: QueryPlan) -> QueryPlan:
    """N166. A month written as an "other" filter on a comparison that already has its periods ("dthu thang 5/2026 so
    vs thang 5/2025 tang hay giam" with other = "thang 5/2025" beside same_period_last_year; train 1, the metrics
    take no such filter): the note goes, the periods stay."""
    if plan.compare is None or plan.compare.kind == "filter":
        return plan
    notes = [f for m in plan.measures for f in m.filters
             if f.field == "other" and isinstance(f.value, str) and _MONTH_NOTE.match(fold(f.value).replace(",", " "))]
    if not notes:
        return plan
    measures = [{**m.model_dump(mode="json", exclude_none=True),
                 "filters": [f.model_dump(mode="json", exclude_none=True) for f in m.filters if f not in notes]}
                for m in plan.measures]
    return _rebuilt(plan, measures=measures)


def debt_added_named(question: str, plan: QueryPlan) -> QueryPlan:
    """N167. "Khách X tháng 8 nợ thêm bao nhiêu, trả được bao nhiêu" with the first figure read as what X still owes
    (debt_amount; train 1, its twins planned debt_added): §4 "Nợ thêm … trong kỳ" is debt_added. Only on a period
    that is a span (not "đến hết ngày"), the question writing "nợ thêm" and the plan no debt_added yet."""
    if plan.intent != "value" or plan.period is None or plan.period.kind in ("until", "today") \
            or any(m.metric == "debt_added" for m in plan.measures):
        return plan
    if not re.search(r"\bno them\b", " ".join(tokens(denoised(question)))):
        return plan
    owed = [m for m in plan.measures if m.metric in ("debt_amount", "debt_total")]
    if len(owed) != 1:
        return plan
    measures = [{**m.model_dump(mode="json", exclude_none=True), "metric": "debt_added"} if m is owed[0]
                else m.model_dump(mode="json", exclude_none=True) for m in plan.measures]
    return _rebuilt(plan, measures=measures)


def nearest_expiry_of_one(plan: QueryPlan) -> QueryPlan:
    """N168. "lô acyclovir stella kem 5% tuýp 5g gần hết hạn nhất có hạn dùng ngày nào" read as a ranking of products by
    nearest expiry filtered to that one product (train 1; no metric ranks so): the date of that product's nearest lot,
    as the hand plans of the same question (value nearest_expiry with the product)."""
    r = plan.rank
    if plan.intent != "rank" or r is None or r.by != "nearest_expiry" or len(plan.measures) != 1:
        return plan
    m = plan.measures[0]
    products = [f for f in m.filters if f.field == "product"]
    if m.metric != "nearest_expiry" or len(products) != 1 or len(m.filters) != 1 or isinstance(products[0].value, list):
        return plan
    raw = plan.model_dump(mode="json", exclude_none=True)
    for k in ("rank", "answer_type", "period"):
        raw.pop(k, None)
    raw["intent"] = "value"
    return QueryPlan.model_validate(raw)


def compared_measure_restated(plan: QueryPlan) -> QueryPlan:
    """N169. "doanh thu ca chiều tăng hay giảm bao nhiêu % so với ca sáng" written with the morning twice: as a second
    measure and as the comparison filter (train 1; the verified plans of the template have one measure, the base in
    compare.filters). The second measure, the same metric under exactly the comparison's filters, goes."""
    c = plan.compare
    if plan.intent != "compare" or c is None or c.kind != "filter" or not c.filters or len(plan.measures) != 2:
        return plan
    first, second = plan.measures
    key = lambda fs: sorted((f.field, str(f.value), f.op) for f in fs)  # noqa: E731
    if first.metric != second.metric or key(second.filters) != key(c.filters) or key(first.filters) == key(c.filters):
        return plan
    return _rebuilt(plan, measures=[first.model_dump(mode="json", exclude_none=True)])


# the measures counted in units of a product: only these have a whole larger unit and base units left (stock.stock_qty)
_SPLIT_METRICS = frozenset({"stock_qty", "quantity", "purchase_minus_sales"})


def split_only_quantities(plan: QueryPlan) -> QueryPlan:
    """N171. "tổng số tiền khách còn nợ ở các đơn đã đặt quá 15 ngày" read with unit_split on debt_total (train 1): an
    amount of money has no whole and odd units, the answer is one number. unit_split goes from a measure not counted in
    units of a product."""
    if not any(m.unit_split and m.metric not in _SPLIT_METRICS for m in plan.measures):
        return plan
    measures = [m.model_dump(mode="json", exclude_none=True) for m in plan.measures]
    for m in measures:
        if m.get("unit_split") and m["metric"] not in _SPLIT_METRICS:
            m["unit_split"] = False
    return _rebuilt(plan, measures=measures)


def unit_particle_restated(plan: QueryPlan) -> QueryPlan:
    """N177. "so ly ban dc bua qua la bao nhieu, cong moi mat hang tinh theo ly ta" read as two measures, quantity in
    "ly" and in "ly ta" (train 1; the template's verified plans have one, quantity in ly): a unit ending in a
    sentence particle (N103) is the unit without it, and a measure equal to another once so read goes."""
    def bare(unit):
        if not isinstance(unit, str):
            return unit
        words = fold(unit).split()
        while len(words) > 1 and words[-1] in _PARTICLES:
            words.pop()
        return " ".join(words) if len(words) < len(fold(unit).split()) else unit
    out, seen = [], []
    for m in plan.measures:
        raw = m.model_dump(mode="json", exclude_none=True)
        raw["unit"] = bare(m.unit)
        if raw.get("unit") is None:
            raw.pop("unit", None)
        key = json.dumps({k: v for k, v in raw.items() if k != "note"}, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.append(key)
        out.append(raw)
    changed = len(out) < len(plan.measures) or any(m.unit != o.get("unit") for m, o in zip(plan.measures, out))
    return _rebuilt(plan, measures=out) if changed else plan


def money_not_asked(question: str, plan: QueryPlan) -> QueryPlan:
    """N178. "quan ban duoc bn ly size l trong thang 4/2025, cong moi mon nhi" read as the quantity in ly and the
    revenue of size L (train 2, refused as metric=revenue): a value plan with a quantity measure beside revenue ones,
    the question writing no money word, is the quantity alone (the template's verified plans)."""
    t = " ".join(tokens(denoised(question)))
    ms = list(plan.measures)
    if plan.intent != "value" or re.search(_MONEY, t) or not any(m.metric == "quantity" for m in ms)             or not any(m.metric == "revenue" for m in ms):
        return plan
    kept = [m.model_dump(mode="json", exclude_none=True) for m in ms if m.metric != "revenue"]
    return _rebuilt(plan, measures=kept)


def split_not_asked(question: str, plan: QueryPlan) -> QueryPlan:
    """N180. "trong tháng 4 năm 2026 cửa hàng bán đc mấy ly sinh tố xoài (m)" read with unit_split (train 1): the whole
    larger units and the base units left are asked as "chẵn" and "lẻ" (§5 tồn theo đơn vị lớn; every train question
    answered as such a pair writes them). Without either word, unit_split goes."""
    if not any(m.unit_split for m in plan.measures):
        return plan
    if re.search(r"\b(?:chan|le)\b", " ".join(tokens(denoised(question)))):
        return plan
    measures = [{**m.model_dump(mode="json", exclude_none=True), "unit_split": False} for m in plan.measures]
    return _rebuilt(plan, measures=measures)


_SPLIT_ASKED = re.compile(r"\b(?:may|bao nhieu|bnhiu|bn|duoc|dc)\s+((?:\w+\s+){0,2}?\w+)\s+chan\b.*\ble\b")


def split_asked(question: str, plan: QueryPlan) -> QueryPlan:
    """N191. "còn mấy hộp chẵn, mấy viên lẻ" read as the stock in viên, one number (prod_train 11/11, 2 wrong: 82
    for [2, 22], 70 for [8, 6]; the template's verified plans have unit = the unit written before "chẵn" and
    unit_split). The inverse of N180: a single stock / quantity measure without unit_split, the question asking for
    whole units ("<đơn vị> chẵn") and the rest ("lẻ"), takes that unit and unit_split."""
    if len(plan.measures) != 1 or plan.measures[0].unit_split or plan.measures[0].metric not in _SPLIT_METRICS:
        return plan
    m = _SPLIT_ASKED.search(" ".join(tokens(denoised(question))))
    if not m:
        return plan
    words = m.group(1).split()
    while words and words[0] in ("may", "bao", "nhieu", "bnhiu", "bn", "duoc", "dc", "con"):
        words.pop(0)
    if not words:
        return plan
    measure = {**plan.measures[0].model_dump(mode="json", exclude_none=True), "unit": " ".join(words), "unit_split": True}
    return _rebuilt(plan, measures=[measure])


def one_period_back(plan: QueryPlan) -> QueryPlan:
    """N181. "doanh thu tết năm nay so vs tết năm trước", "tháng 6 năm 2026 … so vs tháng 6 năm 2025" read with
    compare n = 1, one period back (train 2, the only compare plans with n = 1; every answered one has none): n is the
    length in days the question states ("17 ngày trước Tết", checked against the rule's window), so a 1 beside a kind
    that steps whole periods goes."""
    c = plan.compare
    if c is None or c.n != 1 or c.kind not in ("previous", "same_period_last_year"):
        return plan
    return _rebuilt(plan, compare={**c.model_dump(mode="json", exclude_none=True), "n": None})


_MONTH_YEAR = re.compile(r"\b(\d{1,2})\s+(?:nam\s+)?(\d{4})\b")


def same_month_last_year(question: str, plan: QueryPlan) -> QueryPlan:
    """N182. "dthu thang 6 nam 2026 tang truong bnhiu % so vs thang 6 nam 2025" read as compared with the month before
    (train 1; 25 answered plans of the template compare with same_period_last_year): a month compared with the
    previous one while the question writes that month of the year before is the same period last year."""
    c, p = plan.compare, plan.period
    if plan.intent != "compare" or c is None or c.kind != "previous" or p is None or p.kind != "month" \
            or p.month is None or p.year is None:
        return plan
    named = {(int(m), int(y)) for m, y in _MONTH_YEAR.findall(" ".join(tokens(denoised(question))))}
    if (p.month, p.year - 1) not in named or (p.month - 1 if p.month > 1 else 12,
                                              p.year if p.month > 1 else p.year - 1) in named:
        return plan
    return _rebuilt(plan, compare={**c.model_dump(mode="json", exclude_none=True), "kind": "same_period_last_year"})


_FULL_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def rise_day_written(question: str, plan: QueryPlan) -> QueryPlan:
    """N183. "pharmaton essential hộp 30 viên lên giá 231.500đ từ ngày 20/05/2025; so 30 ngày kể từ ngày tăng giá…"
    planned with the price as the anchor and no day (train 1): the shop keeps no price list, so no day was found,
    while the question writes it. A days_from period anchored by a price, the question writing exactly one full date,
    starts that day (§5 "hiệu ứng tăng giá": the hand plans of questions that write the day have it)."""
    p = plan.period
    if p is None or p.kind != "days_from" or p.date is not None or p.anchor_price is None:
        return plan
    days = set(_FULL_DATE.findall(question))
    if len(days) != 1:
        return plan
    d, m, y = (int(x) for x in days.pop())
    try:
        day = date(y, m, d)
    except ValueError:
        return plan
    period = {**p.model_dump(mode="json", exclude_none=True), "date": day.isoformat()}
    period.pop("anchor_price", None)
    return _rebuilt(plan, period=period)


def months_listed_as_run(question: str, plan: QueryPlan) -> QueryPlan:
    """N185. "dthu 3 tháng liền nhau kết thúc ở tháng 6/2025 là bao nhiêu mỗi tháng" read as the list 2025-04, 2025-05,
    2025-06 (train 1, refused: the question writes no April; 5 verified plans of the template: months, end, n): a list
    of n consecutive months whose last one the question writes, beside "n tháng", is the n months ending there."""
    p = plan.period
    if p is None or p.kind != "months" or not p.months or len(p.months) < 2:
        return plan
    idx = [int(m[:4]) * 12 + int(m[5:7]) - 1 for m in p.months]
    if idx != list(range(idx[0], idx[0] + len(idx))):
        return plan
    t = " ".join(tokens(denoised(question)))
    y, m = divmod(idx[-1], 12)
    if not re.search(rf"\b{len(idx)} thang\b", t) or not re.search(rf"\b{m + 1} (?:nam )?{y}\b", t):
        return plan
    return _rebuilt(plan, period={"kind": "months", "end": p.months[-1], "n": len(idx)})


_DAYS_BEFORE_TET = re.compile(r"\b(\d+)\s+ngay\s+(?:truoc|trc)\s+tet\b")


def days_before_tet(question: str, plan: QueryPlan) -> QueryPlan:
    """N186. "Dịp Tết âm lịch 2026 có doanh thu hơn hay kém 17 ngày trước Tết bao nhiêu %?" read as before_days_from
    with a day the question does not write (train 1, refused): Tết compared with "N ngày trước Tết" is §2's before_tet,
    N kept to cross-check the rule's window (temporal.resolve)."""
    p, c = plan.period, plan.compare
    if p is None or p.kind != "tet" or c is None or c.kind == "before_tet":
        return plan
    ns = set(_DAYS_BEFORE_TET.findall(" ".join(tokens(denoised(question)))))
    if len(ns) != 1:
        return plan
    return _rebuilt(plan, compare={"kind": "before_tet", "n": int(ns.pop()), "output": c.output})


_WEEKDAY_SHORT = re.compile(r"\bt\s?[2-7]\b(?!\s*/)|\bth\s?[2-7]\b(?!\s*/)")


def weekday_not_written(question: str, plan: QueryPlan) -> QueryPlan:
    """N189. "tuần nayf dthu đươc bao nhiêu" planned with weekday in [mon] (train 1, refused: weekday=mon): the week
    read as its first day. A weekday filter the question writes no weekday for ("thứ 2", "chủ nhật", "cuối tuần", "T7"
    not followed by a year) goes."""
    if not any(f.field == "weekday" for m in plan.measures for f in m.filters):
        return plan
    t = fold(question)
    if _WEEKDAY_WORDS.search(t) or _WEEKDAY_SHORT.search(t):
        return plan
    measures = [{**m.model_dump(mode="json", exclude_none=True),
                 "filters": [f.model_dump(mode="json", exclude_none=True) for f in m.filters if f.field != "weekday"]}
                for m in plan.measures]
    return _rebuilt(plan, measures=measures)
