"""N32: an LLM output that breaks the plan schema in a way seen on train, rewritten into the plan it means. Only the
shapes below, each with one reading; anything else stays invalid (no plan). The repaired plan then goes through the
same grounding gates as any other (nlu.accept_plan).

Seen 05/11, 25 train questions the LLM read with no plan, 4 of them invalid:
- a comparison of two filters written as two measures, "compare": {"kind": "filter"} without its filters
  ("doanh thu ca chiều hơn hay kém ca sáng bao nhiêu %"): the first measure is asked, the second is compared;
- a months series written as a range ("kind": "months", "start": "2025-02", "end": "2025-04");
- a count answer typed percent ("số ly size M bán được": answer_type percent where the plan gives a number), when the
  question has no percent word.
"""
from __future__ import annotations

import copy
import re

from .baseline import fold

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_PERCENT = r"%|\b(?:phan tram|chiem|ti trong|ty trong|ti le|ty le)\b"


def _months_between(start: str, end: str) -> int | None:
    a, b = _MONTH.match(start or ""), _MONTH.match(end or "")
    if not a or not b:
        return None
    n = (int(b[1]) - int(a[1])) * 12 + int(b[2]) - int(a[2]) + 1
    return n if 1 <= n <= 36 else None


def _fix_months(period: dict) -> bool:
    if not isinstance(period, dict) or period.get("kind") != "months" or period.get("months") or period.get("n"):
        return False
    n = _months_between(period.get("start"), period.get("end"))
    if n is None:
        return False
    period.pop("start")
    period["n"] = n
    return True


def _fix_compare_filter(raw: dict) -> bool:
    c, ms = raw.get("compare"), raw.get("measures")
    if not isinstance(c, dict) or c.get("kind") != "filter" or c.get("filters") or not isinstance(ms, list):
        return False
    if len(ms) != 2 or not all(isinstance(m, dict) for m in ms):
        return False
    a, b = ms
    rest = lambda m: {k: v for k, v in m.items() if k != "filters"}  # noqa: E731
    if rest(a) != rest(b) or not a.get("filters") or not b.get("filters") or a["filters"] == b["filters"]:
        return False
    c["filters"] = b["filters"]
    raw["measures"] = [a]
    return True


_NUMBER_OF = {"quarter": (re.compile(r"\b(?:quy|q)\s*([1-4])\b"), 4), "month": (re.compile(r"\b(?:thang|th|t)\s*(\d{1,2})\b"), 12)}


def _fill_number(period: dict, question: str) -> bool:
    """A quarter or month period without its number ("Quý 4/2025 …" written {"kind": "quarter", "year": 2025}, public
    06/11): the one number the question gives for it; none or two different ones, no repair."""
    kind = period.get("kind") if isinstance(period, dict) else None
    if kind not in _NUMBER_OF or period.get(kind) is not None:
        return False
    pattern, top = _NUMBER_OF[kind]
    found = {int(n) for n in pattern.findall(fold(question)) if 1 <= int(n) <= top}
    if len(found) != 1:
        return False
    period[kind] = found.pop()
    return True


_MONTH_WORDS = re.compile(r"\b(?:thang|th|t)\s*(\d{1,2})\b")
_SEVERAL = re.compile(r"\b(?:lan luot|moi (?:loai|ben|thu|nhom)|hai so|ca hai|tung)\b")


def _fix_series_months(raw: dict, question: str) -> bool:
    """A series written over one month ("Dthu th7, th8, th9/2025 lần lượt", run10 06/11: 8 such outputs): the months
    the question names, in its order, in the plan's year; consecutive and rising only. The grounding gates still check
    that the question writes that year."""
    p = raw.get("period")
    if raw.get("intent") not in ("series", "trend") or not isinstance(p, dict) or p.get("kind") != "month" \
            or not isinstance(p.get("year"), int):
        return False
    months = [int(m) for m in _MONTH_WORDS.findall(fold(question)) if 1 <= int(m) <= 12]
    if len(months) >= 2 and months == list(range(months[0], months[0] + len(months))):
        raw["period"] = {"kind": "months", "months": [f"{p['year']:04d}-{m:02d}" for m in months]}
        return True
    # across a year, each month with its year (written like "th 12/25", run11 07/11): consecutive, rising, and
    # starting at the plan's month
    from .grounding import stated_months  # late: grounding is the larger module, repair stays importable alone
    pairs = stated_months(question)
    index = [y * 12 + m - 1 for m, y in pairs]
    if len(pairs) < 2 or index != list(range(index[0], index[0] + len(index))) \
            or (pairs[0][1], pairs[0][0]) != (p["year"], p.get("month")):
        return False
    raw["period"] = {"kind": "months", "months": [f"{y:04d}-{m:02d}" for m, y in pairs]}
    return True


def _fix_cancel_share(raw: dict) -> bool:
    """"đơn bị huỷ chiếm mấy %" written as [cancel_count, order_count] (or cancel_count alone) typed percent: the
    cancel rate (§1), the only percent those measures make (run10: 6 such outputs)."""
    ms = raw.get("measures")
    if raw.get("answer_type") != "percent" or not isinstance(ms, list) or not ms or not isinstance(ms[0], dict):
        return False
    metrics = [m.get("metric") for m in ms if isinstance(m, dict)]
    if metrics not in (["cancel_count"], ["cancel_count", "order_count"]):
        return False
    kept = [f for f in ms[0].get("filters") or [] if not (isinstance(f, dict) and f.get("field") == "order_status")]
    raw["measures"] = [{"metric": "cancel_rate", "filters": kept}]
    return True


def _fix_warranty_share(raw: dict) -> bool:
    """N102. §6 Điện thoại "lượt bảo hành so với số máy bán chiếm bnhiu %" written as [warranty_count, quantity] typed
    percent (public run11, both readings): the warranty rate, the only percent those measures make (§6 "Tỉ lệ bảo
    hành = số lượt bảo hành trong quý / số máy bán trong quý")."""
    ms = raw.get("measures")
    if raw.get("answer_type") != "percent" or not isinstance(ms, list) or len(ms) != 2:
        return False
    if [m.get("metric") if isinstance(m, dict) else None for m in ms] not in (
            ["warranty_count", "quantity"], ["quantity", "warranty_count"]):
        return False
    if any(not (isinstance(f, dict) and f.get("field") == "order_status") for m in ms for f in m.get("filters") or []):
        return False
    raw["measures"] = [{"metric": "warranty_rate", "filters": []}]
    return True


def _fix_threshold_count(raw: dict, question: str) -> bool:
    """N104. Of a month's buyers, the percent with N orders or more, written with the customers counted as a measure
    (customer_count, filter order_status completed) beside a threshold on their orders (public run11, both readings;
    the contract wants the threshold's own metric or none): the customers passing the bound, as a share of every
    customer when the question asks a percent (as the train plans of this template). Customers and their orders or
    money only."""
    t, ms = raw.get("threshold"), raw.get("measures")
    if raw.get("intent") != "count_where" or not isinstance(t, dict) or not isinstance(ms, list) or len(ms) != 1:
        return False
    m = ms[0]
    if not isinstance(m, dict) or t.get("entity") != "customer" or m.get("metric") != "customer_count" \
            or t.get("metric") not in ("order_count", "revenue") \
            or any(not (isinstance(f, dict) and f.get("field") == "order_status") for f in m.get("filters") or []):
        return False
    raw.pop("measures")
    raw.pop("answer_type", None)
    if "%" in question or re.search(_PERCENT, fold(question)):
        t["as_share"] = True
    return True


def repair(raw: dict, question: str, error: str) -> dict | None:
    """The repaired output, or None when `error` is none of the known shapes or the repair does not apply."""
    if not isinstance(raw, dict):
        return None
    out = copy.deepcopy(raw)
    fixed = False
    if "months hoặc end + n" in error:
        fixed |= _fix_months(out.get("period") or {})
        fixed |= _fix_months((out.get("compare") or {}).get("period") or {})
    if "compare filter cần trường filters" in error:
        fixed |= _fix_compare_filter(out)
    if "thiếu ['quarter']" in error or "thiếu ['month']" in error:
        fixed |= _fill_number(out.get("period") or {}, question)
    if "cần period kind months" in error:
        fixed |= _fix_series_months(out, question)
    if "khác measures[0].metric" in error and error.lstrip().find("threshold.metric") >= 0:
        fixed |= _fix_threshold_count(out, question)
    m = re.search(r"answer_type=(\w+) mâu thuẫn với plan \(suy ra (\w+)\)", error)
    if m and m[1] == "percent" and m[2] == "list":
        fixed |= _fix_cancel_share(out) or _fix_warranty_share(out)
    elif m and m[1] == "percent" and m[2] == "number" and not re.search(_PERCENT, fold(question)):
        out.pop("answer_type", None)
        fixed = True
    elif m and m[2] == "number" and m[1] in ("list", "date") and not _SEVERAL.search(fold(question)):
        # the answer type is optional and the plan's shape decides it (one figure); the gates still judge the plan
        out.pop("answer_type", None)
        fixed = True
    return out if fixed else None
