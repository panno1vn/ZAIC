"""[C2] Turn the plan's symbolic periods into dates, following rulebook §2 and calendar.csv. Work package G4.

Skeleton (05/11): day, today, yesterday, month, quarter, year (with the §2 rule for a month or quarter without a
year); flow periods are clipped at as_of_date (records after today have not happened). Every other kind, any
compare and any series return None, so those questions abstain until G4 adds them.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta
from pathlib import Path

from datamate.contracts import CanonicalDB, PeriodExpr, QueryPlan, ResolvedPeriod, ResolvedPlan

STOCK_KINDS = {"until"}


def _year_for(month: int, as_of: date) -> int:
    """§2: a month without a year is this year's unless that is after today, then last year's."""
    return as_of.year if month <= as_of.month else as_of.year - 1


def resolve_period(p: PeriodExpr, as_of: date) -> ResolvedPeriod | None:
    k = p.kind
    if k == "today":
        start = end = as_of
    elif k == "yesterday":
        start = end = as_of - timedelta(days=1)
    elif k == "day":
        start = end = date.fromisoformat(p.date)
    elif k == "month":
        y = p.year or _year_for(p.month, as_of)
        start, end = date(y, p.month, 1), date(y, p.month, _cal.monthrange(y, p.month)[1])
    elif k == "quarter":
        first = 3 * (p.quarter - 1) + 1
        y = p.year or _year_for(first, as_of)
        start, end = date(y, first, 1), date(y, first + 2, _cal.monthrange(y, first + 2)[1])
    elif k == "year":
        start, end = date(p.year, 1, 1), date(p.year, 12, 31)
    else:
        return None
    if start > as_of:
        return None  # a period entirely after today has no data yet
    return ResolvedPeriod(start=start, end=min(end, as_of), mode="flow", label=f"{k} {start}..{min(end, as_of)}")


def resolve(plan: QueryPlan, as_of: date, calendar_csv: Path, db: CanonicalDB | None = None) -> ResolvedPlan | None:
    """ResolvedPlan with the period as dates, or None when a period cannot be resolved yet.

    `db` is needed only for periods anchored in the data (days_from + anchor_price: the day the price rose, §5).
    """
    if plan.compare is not None:
        return None
    period = None
    if plan.period is not None:
        period = resolve_period(plan.period, as_of)
        if period is None:
            return None
    return ResolvedPlan(plan=plan, as_of=as_of, period=period)
