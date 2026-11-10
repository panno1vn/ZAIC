"""Rule-based question parser: a few frequent question shapes, recognised only when nothing else is in the question.

Used when no LLM is available, and later by G3 as a cross-check of the LLM's plan. Precision first: any word it
does not know (a product name, a customer, a unit…) makes it return None, so the question abstains instead of being
answered without its filter.
"""
from __future__ import annotations

import re

from datamate.contracts import QueryPlan

from .templates import tokens

ABBREVIATIONS = [
    (r"\bdthu\b|\bdt\b|\brevenue\b", "doanh thu"), (r"\bbnhiu\b|\bbn\b|\bbao nhiu\b|\bbnhieu\b", "bao nhieu"),
    (r"\bnhiu\b", "nhieu"), (r"\bdc\b|\bdk\b", "duoc"), (r"\bhnay\b|\bbua nay\b|\bhom ni\b", "hom nay"),
    (r"\bhqua\b|\bbua qua\b", "hom qua"), (r"\bsp\b", "san pham"), (r"\bbill?\b", "don"),
]
# words that may appear around the recognised shapes without changing their meaning
FILLER = set("""
e oi a ah a z vay nhe nhi ha ta the do nha hen ne ho cho toi minh em anh chi biet hoi xem giup gium dum check coi
la bao nhieu tong cong cua cua hang tiem quan shop ban duoc tien thu ve doanh thu so don hang may trong ngay thang
nam quy hom nay qua nao cao nhat nhieu mat san pham chay top nhung gi cai co duoc vao ve tat ca toan bo
""".split())


def fold(text: str) -> str:
    """Lower case, no diacritics, telex typed without the input method undone ("thangs", "dduwowcj": N7, 0 of 290
    such train questions were read before), abbreviations expanded; words and digit runs only."""
    t = " ".join(tokens(text))
    for pat, rep in ABBREVIATIONS:
        t = re.sub(pat, rep, t)
    return " ".join(re.findall(r"[a-z]+|\d+", t))


def _period(t: str) -> tuple[dict | None, str]:
    """Period found in the folded text, and the text with it removed."""
    rules = [
        (r"\b(?:thang|th|t)\s*(\d{1,2})\s*(?:nam\s*)?(\d{4})\b", lambda m: {"kind": "month", "month": int(m[1]), "year": int(m[2])}),
        (r"\bquy\s*(\d)\s*(?:nam\s*)?(\d{4})\b", lambda m: {"kind": "quarter", "quarter": int(m[1]), "year": int(m[2])}),
        (r"\bhom nay\b", lambda m: {"kind": "today"}),
        (r"\bhom qua\b", lambda m: {"kind": "yesterday"}),
    ]
    for pat, make in rules:
        m = re.search(pat, t)
        if m:
            return make(m), (t[:m.start()] + " " + t[m.end():])
    return None, t


SHAPES = [  # (pattern on the folded text without its period, plan without period)
    (r"\bngay nao\b.*\b(?:doanh thu|tien)\b.*\b(?:cao nhat|nhieu (?:tien )?nhat)\b"
     r"|\b(?:doanh thu|tien)\b.*\bngay nao\b.*\b(?:cao nhat|nhieu nhat)\b"
     r"|\bngay nao\b.*\bban duoc nhieu tien nhat\b",
     {"intent": "rank", "rank": {"entity": "day", "by": "revenue"}, "measures": [{"metric": "revenue"}]}),
    (r"\b(?:mat hang|hang|san pham)\b.*\b(?:ban chay nhat|chay nhat|ban nhieu nhat)\b",
     {"intent": "rank", "rank": {"entity": "product", "by": "quantity"}, "measures": [{"metric": "quantity"}]}),
    (r"\b(?:so don|may don|bao nhieu don)\b",
     {"intent": "value", "measures": [{"metric": "order_count"}]}),
    (r"\bdoanh thu\b|\bban duoc\b.*\btien\b|\bthu ve\b.*\btien\b",
     {"intent": "value", "measures": [{"metric": "revenue"}]}),
]


# "ngày nào", "cao nhất": left over after a value shape, the question asks which one, not how much
WHICH_WORDS = {"nao", "nhat"}


# N129. A question asking whether the revenue rose over three named months, each above the one before, asks a trend (the revenue of
# three months each above the one before), in words the LLM reads as a comparison with the months as products (public,
# 2 questions, both refused by the gates on both calls; train has no question of this shape). Only revenue, two "cao
# hơn", a yes / no ending and exactly three months written that follow each other.
_CHAIN_MONTH = re.compile(r"\b(?:t|th|thang)\s*(\d{1,2})\s+(\d{4}|\d{2})\b")
_CHAIN_YESNO = re.compile(r"\b(?:dung (?:vay |ko |khong )?(?:khong|ko|k)|phai (?:khong|ko|k))\s*$")


def _chained_rise(t: str) -> QueryPlan | None:
    if len(re.findall(r"\bcao hon\b", t)) != 2 or not _CHAIN_YESNO.search(t) \
            or not re.search(r"\b(?:doanh thu|dthu|dt)\b", t) or re.search(r"\b(?:thap hon|giam)\b", t):
        return None
    months = sorted({(int(y) + (2000 if len(y) == 2 else 0), int(m)) for m, y in _CHAIN_MONTH.findall(t)})
    if len(months) != 3 or not all(1 <= m <= 12 for _, m in months):
        return None
    index = [y * 12 + m for y, m in months]
    if index != list(range(index[0], index[0] + 3)):
        return None
    return QueryPlan.model_validate({"intent": "trend", "measures": [{"metric": "revenue"}],
                                     "period": {"kind": "months", "months": [f"{y}-{m:02d}" for y, m in months]}})


def parse(question: str) -> QueryPlan | None:
    t = fold(question)
    if (chained := _chained_rise(t)) is not None:
        return chained
    period, rest = _period(t)
    if period is None:
        return None
    if any(w not in FILLER for w in rest.split()):  # an unknown word may be a filter: do not guess
        return None
    for pattern, plan in SHAPES:
        if re.search(pattern, rest):
            if plan["intent"] == "value" and WHICH_WORDS & set(rest.split()):
                return None  # a ranking this parser does not know, e.g. "doanh thu cao nhất là ngày nào"
            try:
                return QueryPlan.model_validate({**plan, "period": period})
            except Exception:
                return None
    return None


# N158. Readings used only when the LLM gives no plan at all (its output broken past repair, or refused on both calls):
# shapes the verified train bank plans one way every time, read here from the words.
_SHARE_BY_ORDERS = re.compile(r"\b(?:mua|dat)\s+(tu|it nhat|tren)\s+(\d+)\s+don\b")
_OVERDUE_WHO = re.compile(r"\b(?:may|mi|bao nhieu|bn|bnhiu|bnhieu)\s+(?:khach|nguoi|ngui)\b")
_DAY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def fallback(question: str) -> QueryPlan | None:
    t = fold(question)
    # Of the customers who bought in a month, the percent with N orders or more: the share of the month's buyers with N orders or more (train
    # bank: every such question, e.g. "trong số khách đã mua hàng tháng 7/2026, bnhiu % mua từ 8 đơn trở lên", planned
    # as this count_where)
    m = _SHARE_BY_ORDERS.search(t)
    if m and re.search(r"\bkhach\b", t) and ("%" in question or re.search(r"\bphan tram\b", t)):
        period, _ = _period(t)
        if period is not None:
            return QueryPlan.model_validate({
                "intent": "count_where", "period": period,
                "threshold": {"entity": "customer", "metric": "order_count", "op": "gt" if m[1] == "tren" else "gte",
                              "value": float(m[2]), "as_share": True}})
    # "hết ngày 8/2/2026 shop có mấy người trả góp còn kỳ quá hạn chưa đóng": the customers with an overdue instalment
    # (§6 Trả góp), as public plans its siblings (other wordings of the same count)
    if _OVERDUE_WHO.search(t) and re.search(r"\bgop\b", t) and re.search(r"\bqua han\b", t) and not re.search(
            r"\b(?:tien|bao nhieu tien)\b", t):
        days = _DAY.findall(question)
        if len(days) == 1:
            d, mo, y = (int(x) for x in days[0])
            return QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "overdue_installment_count"}],
                                             "period": {"kind": "until", "date": f"{y:04d}-{mo:02d}-{d:02d}"}})
    return None
