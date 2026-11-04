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


def parse(question: str) -> QueryPlan | None:
    t = fold(question)
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
