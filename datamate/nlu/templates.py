"""Question templates: the train questions are generated from a few hundred templates filled with names, numbers and
dates (T1, docs/research/templates.md). A question's template text has names, numbers and filler words masked; a
plan's shape has its values masked. Used to group train questions into templates (tools/research/templates.py) and,
in T4, to find a verified "twin" question of a new question.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

from datamate.contracts import QueryPlan

# telex typed without the input method: a tone key ends the word ("thangs", "toongr", "dduwowcj"), a 'w' follows the
# vowel it marks ("tawng", "nawm"); unaccented Vietnamese words never end in s, f, r, x, j
_TONE_KEY = re.compile(r"(?<=[a-z]{2})[sfrxj]$")
_HOOK_KEY = re.compile(r"(?<=[aou])w")
_DOUBLE = re.compile(r"([a-z])\1")

SYNONYMS = [  # on the template text (numbers masked, telex undone); only rewrites with one meaning
    (r"\bdthu\b|\bdt\b|\brevenue\b", "doanh thu"), (r"\bbnhiu\b|\bbn\b|\bbao nhiu\b|\bbnhieu\b", "bao nhieu"),
    (r"\bnhiu\b", "nhieu"), (r"\bdc\b|\bdk\b", "duoc"), (r"\bhnay\b|\bbua nay\b|\bhom ni\b", "hom nay"),
    (r"\bhqua\b|\bbua qua\b", "hom qua"), (r"\btrc\b", "truoc"), (r"\bvs\b", "voi"), (r"\bsp\b", "san pham"),
    (r"\bbil\b|\borde\b", "don"), (r"\bth\b(?= #| truoc| nay)", "thang"), (r"%", "phan tram"),
    (r"\bbinh quan\b", "trung binh"), (r"\btoi het\b", "den het"), (r"\bko\b|\bk\b|\bhok\b|\bkhg\b", "khong"),
    (r"\bmay\b", "bao nhieu"),
]
# openers, particles and the shop's own name ("cho tôi biết", "xem giúp", "nhỉ", "z", "cửa hàng"): the same template is
# written with or without them. Words that change what is asked ("không", "chi", "thẻ", "tối") never go here.
FILLER_PHRASES = re.compile(
    r"\b(?:(?:cho|giup|gium) (?:toi|minh|em|hoi)(?: (?:biet|hoi|xem))?|(?:xem|coi|check|dem|tinh) (?:giup|gium|dum|ho)"
    r"(?: (?:toi|minh|em))?|cua hang|cua tiem|nha thuoc|tiem|quan|shop)\b")
FILLER = frozenset("e oi a ah z vay nhe nhi ha ta nha hen ne ho la cua giup gium dum coi xem check".split())
_MONEY_UNIT = frozenset({"k", "tr", "trieu", "d", "dong", "vnd", "nghin", "ngan"})


def fold(text: str) -> str:
    """Lower case, no diacritics, đ -> d."""
    t = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in t if not unicodedata.combining(c))


def _untelex(word: str) -> str:
    if not word.isalpha() or len(word) < 3:
        return word
    w = _HOOK_KEY.sub("", _TONE_KEY.sub("", word))
    return _DOUBLE.sub(r"\1", w)


def tokens(text: str) -> list[str]:
    """Folded words and digit runs, telex typos undone: "Tháng 7/2025 dduwowcj" -> thang 7 2025 duoc."""
    return [_untelex(t) for t in re.findall(r"[a-z]+|\d+|%", fold(text))]


class NameIndex:
    """Names found in a business's data (products, groups, customers…), each with a role tag, matched as whole token
    runs. A one-word name is only masked after a word that announces it ("nhóm trà"), since many one-word names are
    also common words ("trà" folds to "tra" like "trả")."""

    CUES = {"NHOM": ("nhom", "nhom hang", "nhom mon", "nhom thuoc", "loai", "danh muc"),
            "HC": ("hoat chat", "thanh phan"), "KH": ("khach", "khach hang"), "NV": ("nhan vien", "nv", "tho"),
            "NCC": ("cung cap", "ncc"), "NHOMKH": ("nhom", "khach")}

    def __init__(self, names: Iterable[tuple[str, str]] = ()):
        self._by_first: dict[str, list[tuple[tuple[str, ...], str]]] = defaultdict(list)
        for role, name in names:
            role, toks = role.upper(), tuple(tokens(name))  # upper case: never rewritten by SYNONYMS
            if toks and not (len(toks) == 1 and len(toks[0]) < 3) and not all(t.isdigit() for t in toks):
                self._by_first[toks[0]].append((toks, role))
        for cands in self._by_first.values():
            cands.sort(key=lambda c: -len(c[0]))
        self._cues = {r: [tuple(c.split()) for c in cs] for r, cs in self.CUES.items()}

    def _cued(self, out: list[str], role: str) -> bool:
        return any(tuple(out[-len(c):]) == c for c in self._cues.get(role, ()))

    def mask(self, toks: list[str]) -> list[str]:
        """The tokens with every known name replaced by <role>, longest name first."""
        out, i = [], 0
        while i < len(toks):
            for name, role in self._by_first.get(toks[i], ()):
                if tuple(toks[i:i + len(name)]) == name and (len(name) > 1 or self._cued(out, role)):
                    out.append(f"<{role}>")
                    i += len(name)
                    break
            else:
                out.append(toks[i])
                i += 1
        return out


def template_text(question: str, names: NameIndex | None = None) -> str:
    """The question with names, numbers and filler masked or dropped: what is left is its template.
    "Tháng 7/2025 Bia Tiger bán đc bn lon z" -> "thang # <SP> ban duoc bao nhieu lon"."""
    toks = tokens(question)
    if names is not None:
        toks = names.mask(toks)
    out: list[str] = []
    for t in toks:
        if t.isdigit():
            if not out or out[-1] != "#":
                out.append("#")
        elif t in _MONEY_UNIT and out and out[-1] == "#":
            out.append("tien")
        else:
            out.append(t)
    text = " ".join(out)
    for pat, rep in SYNONYMS:
        text = re.sub(pat, rep, text)
    text = FILLER_PHRASES.sub(" ", text)
    return " ".join(t for t in text.split() if t not in FILLER)


def _filter_shape(filters) -> str:
    fields = sorted({f.field + ("" if f.op == "eq" else f".{f.op}") for f in filters or []})
    return "[" + ",".join(fields) + "]" if fields else ""


def _measure_shape(m) -> str:
    s = m.metric + _filter_shape(m.filters)
    if m.unit:
        s += "/unit"
    if m.aggregate != "total":
        s += f"/{m.aggregate}"
    if m.unit_split:
        s += "/split"
    return s


def plan_shape(plan: QueryPlan, period: bool = True) -> str:
    """What a plan asks for with its values masked: intent, metrics and the fields they filter on, period kind,
    comparison, ranking / threshold / list shape. Two questions of one template have plans of one shape.
    "value | revenue[product] | month". Without `period` the period kind is left out: one metric function serves
    every period kind (the temporal engine resolves them)."""
    parts = [plan.intent]
    own = plan.rank.by if plan.rank else plan.threshold.metric if plan.threshold else None
    measures = [_measure_shape(m) for m in plan.measures]
    if own and measures == [own]:
        measures = []  # the measure only repeats the ranking / threshold metric
    if plan.rank:
        r = plan.rank
        k = "all" if r.k is None else "1" if r.k == 1 else "k"
        parts.append(f"{r.entity} by {r.by} k={k} {r.order}" + (" +values" if r.with_values else "")
                     + (" min_orders" if r.min_orders else ""))
    if plan.threshold:
        t = plan.threshold
        parts.append(f"{t.entity} {t.metric} {t.op}" + (" as_share" if t.as_share else ""))
    if plan.list_spec:
        ls = plan.list_spec
        parts.append(f"{ls.entity} {ls.condition}" + (" count" if ls.count else ""))
    if measures:
        parts.append(" + ".join(measures))
    if plan.share_of:
        parts.append("of " + _measure_shape(plan.share_of))
    if period:
        parts.append(plan.period.kind if plan.period else "-")
    if plan.compare:
        c = plan.compare
        parts.append(f"vs {c.kind}{_filter_shape(c.filters)} {c.output}" + (f" {c.period.kind}" if c.period else ""))
    return " | ".join(parts)
