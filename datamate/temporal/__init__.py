"""[C2] Turn the plan's symbolic periods into dates, following rulebook §2 and calendar.csv. Work package G4.

Every period kind and compare kind of the contract (v1.1) except `days_from` with `anchor_price` (the day a price rose
needs the linked product: done with the price-effect metrics). Flow periods are clipped at as_of_date: records after
today have not happened. Metrics of STOCK_METRICS are always a state at the end of a day, from the start of the data.
Whatever cannot be resolved returns None, so the question abstains.
"""
from __future__ import annotations

import calendar as _cal
import csv
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from datamate.contracts import STOCK_METRICS, CanonicalDB, PeriodExpr, QueryPlan, ResolvedPeriod, ResolvedPlan

DATA_START = date(2000, 1, 1)  # start of a stock period: "từ đầu dữ liệu" (every shop's data starts later)
STOCK_KINDS = {"until"}
DAY = timedelta(days=1)


def _month_end(y: int, m: int) -> date:
    return date(y, m, _cal.monthrange(y, m)[1])


def _add_months(y: int, m: int, k: int) -> tuple[int, int]:
    n = y * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


def _year_for(month: int, as_of: date) -> int:
    """§2: a month without a year is this year's unless that is after today, then last year's."""
    return as_of.year if month <= as_of.month else as_of.year - 1


def _bound(s: str, end: bool) -> date:
    """'YYYY-MM-DD' as is; 'YYYY-MM' as the first (or last) day of that month."""
    if len(s) == 7:
        y, m = int(s[:4]), int(s[5:])
        return _month_end(y, m) if end else date(y, m, 1)
    return date.fromisoformat(s)


def _minus_year(d: date) -> date:
    return d.replace(year=d.year - 1) if not (d.month == 2 and d.day == 29) else date(d.year - 1, 2, 28)


@lru_cache(maxsize=4)
def lunar_dates(calendar_csv: str) -> dict[tuple[int, int, int], date]:
    """(lunar year, lunar month, lunar day) -> solar date, from the split's calendar.csv (non-leap months)."""
    out = {}
    path = Path(calendar_csv)
    if not path.exists():
        return out
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("lunar_leap", "")).strip().lower() in ("true", "1"):
                continue
            out[(int(r["lunar_year"]), int(r["lunar_month"]), int(r["lunar_day"]))] = date.fromisoformat(r["date"])
    return out


def tet_window(lunar_year: int, calendar_csv: Path | str) -> tuple[date, date] | None:
    """§2 "Tết năm Y": from 23 tháng Chạp of lunar year Y − 1 to the end of mùng 10 tháng Giêng of lunar year Y."""
    cal = lunar_dates(str(calendar_csv))
    start, end = cal.get((lunar_year - 1, 12, 23)), cal.get((lunar_year, 1, 10))
    return (start, end) if start and end else None


def raw_span(p: PeriodExpr, as_of: date, calendar_csv: Path | str | None = None) -> tuple[date, date] | None:
    """The period's first and last day before clipping at today, or None when it cannot be resolved."""
    k = p.kind
    if k == "today":
        return as_of, as_of
    if k == "yesterday":
        return as_of - DAY, as_of - DAY
    if k in ("day", "until"):
        d = date.fromisoformat(p.date)
        return d, d
    if k == "this_week":
        return as_of - timedelta(days=as_of.weekday()), as_of
    if k == "last_week":
        monday = as_of - timedelta(days=as_of.weekday() + 7)
        return monday, monday + timedelta(days=6)
    if k == "this_month":
        return as_of.replace(day=1), as_of
    if k == "last_month":
        y, m = _add_months(as_of.year, as_of.month, -1)
        return date(y, m, 1), _month_end(y, m)
    if k == "month":
        y = p.year or _year_for(p.month, as_of)
        return date(y, p.month, 1), _month_end(y, p.month)
    if k == "quarter":
        first = 3 * (p.quarter - 1) + 1
        y = p.year or _year_for(first, as_of)
        return date(y, first, 1), _month_end(y, first + 2)
    if k == "year":
        return date(p.year, 1, 1), date(p.year, 12, 31)
    if k == "ytd":
        return date(as_of.year, 1, 1), as_of
    if k == "last_n_days":
        return as_of - timedelta(days=p.n - 1), as_of
    if k == "next_n_days":
        return as_of, as_of + timedelta(days=p.n)  # §6 "hết hạn trong N ngày tới": từ D đến hết D + N
    if k == "range":
        start, end = _bound(p.start, end=False), _bound(p.end, end=True)
        return (start, end) if start <= end else None
    if k == "months":
        months = month_list(p)
        if not months:
            return None
        (y0, m0), (y1, m1) = months[0], months[-1]
        return date(y0, m0, 1), _month_end(y1, m1)
    if k == "days_from":
        if p.date is None:  # anchored on a price rise: needs the linked product (price-effect metrics)
            return None
        d = date.fromisoformat(p.date)
        return d, d + timedelta(days=p.n - 1)
    if k == "tet":
        if calendar_csv is None:
            return None
        return tet_window(p.lunar_year or as_of.year, calendar_csv)
    return None  # "all" and anything new: not resolved yet


def month_list(p: PeriodExpr) -> list[tuple[int, int]]:
    """The months of a "months" period, in order: the explicit list, or the n months ending at `end`."""
    if p.months:
        return [(int(s[:4]), int(s[5:])) for s in p.months]
    if p.end and p.n:
        y, m = int(p.end[:4]), int(p.end[5:])
        return [_add_months(y, m, -i) for i in range(p.n - 1, -1, -1)]
    return []


def _flow(start: date, end: date, as_of: date, label: str) -> ResolvedPeriod | None:
    if start > as_of:
        return None  # a period entirely after today has no data yet
    return ResolvedPeriod(start=start, end=min(end, as_of), mode="flow", label=label)


def resolve_period(p: PeriodExpr, as_of: date, calendar_csv: Path | str | None = None, stock: bool = False
                   ) -> ResolvedPeriod | None:
    span = raw_span(p, as_of, calendar_csv)
    if span is None:
        return None
    start, end = span
    if stock or p.kind in STOCK_KINDS:  # §2 "đến hết ngày X": every record from the start of the data to the end of X
        end = min(end, as_of)
        return ResolvedPeriod(start=DATA_START, end=end, mode="stock", label=f"stock …{end}")
    if p.kind == "next_n_days":
        return ResolvedPeriod(start=start, end=end, mode="flow", label=f"next {start}..{end}")
    return _flow(start, end, as_of, f"{p.kind} {start}..{min(end, as_of)}")


def _length(period: ResolvedPeriod) -> int:
    return (period.end - period.start).days + 1


def compare_period(plan: QueryPlan, period: ResolvedPeriod, as_of: date, calendar_csv: Path | str | None
                   ) -> ResolvedPeriod | None:
    """The period the asked figure is compared with (§1 "kỳ trước", §2 "tháng này so với tháng trước", Tết)."""
    c, p = plan.compare, plan.period
    kind = c.kind
    if kind == "filter":
        return period
    if kind == "period":
        return resolve_period(c.period, as_of, calendar_csv) if c.period else None
    if p is None:
        return None
    month_clipped = p.kind == "month" and period.end < _month_end(period.end.year, period.end.month)
    if kind == "previous_same_days" or (kind == "previous" and (p.kind == "this_month" or month_clipped)):
        if period.start.day != 1 or (period.start.year, period.start.month) != (period.end.year, period.end.month):
            return None
        y, m = _add_months(period.start.year, period.start.month, -1)
        last = _month_end(y, m)
        return _flow(date(y, m, 1), date(y, m, min(period.end.day, last.day)), as_of, "previous same days")
    if kind == "previous":
        s, e = period.start, period.end
        if p.kind in ("today", "yesterday", "day"):
            return _flow(s - DAY, e - DAY, as_of, "previous day")
        if p.kind in ("this_week", "last_week"):
            return _flow(s - timedelta(days=7), e - timedelta(days=7), as_of, "previous week")
        if p.kind in ("month", "last_month"):
            y, m = _add_months(s.year, s.month, -1)
            return _flow(date(y, m, 1), _month_end(y, m), as_of, "previous month")
        if p.kind == "quarter":
            y, m = _add_months(s.year, s.month, -3)
            y2, m2 = _add_months(y, m, 2)
            return _flow(date(y, m, 1), _month_end(y2, m2), as_of, "previous quarter")
        if p.kind == "year":
            return _flow(date(s.year - 1, 1, 1), date(s.year - 1, 12, 31), as_of, "previous year")
        if p.kind in ("last_n_days", "range"):
            n = _length(period)
            return _flow(s - timedelta(days=n), s - DAY, as_of, "previous same length")
        if p.kind == "tet":
            kind = "same_period_last_year"  # "kỳ trước" of a Tết is the Tết before it
        else:
            return None  # ytd, months, until…: "kỳ trước" has no single meaning here
    if kind == "same_period_last_year":
        if p.kind == "tet":
            span = tet_window((p.lunar_year or as_of.year) - 1, calendar_csv) if calendar_csv else None
            return _flow(span[0], span[1], as_of, "previous Tết") if span else None
        return _flow(_minus_year(period.start), _minus_year(period.end), as_of, "same period last year")
    if kind == "before_tet":
        if p.kind != "tet":
            return None
        n = _length(period)
        return _flow(period.start - timedelta(days=n), period.start - DAY, as_of, "before Tết")
    if kind == "before_days_from":
        if p.kind != "days_from" or p.n is None:
            return None
        return _flow(period.start - timedelta(days=p.n), period.start - DAY, as_of, "before D")
    return None


def is_stock(plan: QueryPlan) -> bool:
    return any(m.metric in STOCK_METRICS for m in plan.measures) or (
        plan.rank is not None and plan.rank.by in STOCK_METRICS)


def resolve(plan: QueryPlan, as_of: date, calendar_csv: Path | str | None = None, db: CanonicalDB | None = None
            ) -> ResolvedPlan | None:
    """ResolvedPlan with every period as dates, or None when a period cannot be resolved (the question abstains).

    `db` is kept for periods anchored in the data (days_from + anchor_price), resolved with the price-effect metrics.
    """
    stock = is_stock(plan)
    period = None
    if plan.period is not None:
        period = resolve_period(plan.period, as_of, calendar_csv, stock=stock)
        if period is None:
            return None
    elif stock:  # "còn tồn bao nhiêu", no period: the state at the end of today
        period = ResolvedPeriod(start=DATA_START, end=as_of, mode="stock", label=f"stock …{as_of}")
    series: list[ResolvedPeriod] = []
    if plan.period is not None and plan.period.kind == "months":
        for y, m in month_list(plan.period):
            one = _flow(date(y, m, 1), _month_end(y, m), as_of, f"{y}-{m:02d}")
            if one is None:
                return None
            series.append(one)
    compare = None
    if plan.compare is not None:
        compare = compare_period(plan, period, as_of, calendar_csv) if period is not None else None
        if compare is None:
            return None
        if plan.compare.n is not None and plan.compare.kind != "filter" and _length(compare) != plan.compare.n:
            return None  # "17 ngày trước Tết" must agree with the rule's window, else one of the two readings is wrong
    return ResolvedPlan(plan=plan, as_of=as_of, period=period, compare_period=compare, series=series)
