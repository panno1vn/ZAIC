"""[C2] one test (at least) per row of rulebook §2, plus the compare periods and STOCK_METRICS."""
from datetime import date
from pathlib import Path

import pytest

from datamate.contracts import QueryPlan
from datamate.temporal import DATA_START, resolve, tet_window

CAL = Path(__file__).resolve().parents[1] / "data" / "train" / "calendar.csv"
THU = date(2026, 8, 27)  # a Thursday


def span(period: dict, as_of: date = THU, metric: str = "revenue", compare: dict | None = None):
    raw = {"intent": "compare" if compare else "value", "measures": [{"metric": metric}], "period": period}
    if compare:
        raw["compare"] = compare
    r = resolve(QueryPlan.model_validate(raw), as_of, CAL)
    if r is None:
        return None
    out = (r.period.start, r.period.end, r.period.mode)
    return (out, (r.compare_period.start, r.compare_period.end)) if compare else out


@pytest.mark.parametrize("period,expected", [
    ({"kind": "today"}, (THU, THU, "flow")),                                              # ngày X, hôm nay, hôm qua
    ({"kind": "yesterday"}, (date(2026, 8, 26), date(2026, 8, 26), "flow")),
    ({"kind": "day", "date": "2026-08-01"}, (date(2026, 8, 1), date(2026, 8, 1), "flow")),
    ({"kind": "range", "start": "2026-08-03", "end": "2026-08-09"},                        # từ X đến Y: gồm cả X và Y
     (date(2026, 8, 3), date(2026, 8, 9), "flow")),
    ({"kind": "range", "start": "2026-02", "end": "2026-04"}, (date(2026, 2, 1), date(2026, 4, 30), "flow")),
    ({"kind": "last_n_days", "n": 7}, (date(2026, 8, 21), THU, "flow")),                  # N ngày gần nhất, kể cả hôm nay
    ({"kind": "this_week"}, (date(2026, 8, 24), THU, "flow")),                             # tuần bắt đầu thứ Hai
    ({"kind": "last_week"}, (date(2026, 8, 17), date(2026, 8, 23), "flow")),               # cả tuần liền trước
    ({"kind": "month", "year": 2026, "month": 2}, (date(2026, 2, 1), date(2026, 2, 28), "flow")),  # cả tháng
    ({"kind": "month", "year": 2026, "month": 8}, (date(2026, 8, 1), THU, "flow")),        # sau hôm nay chưa xảy ra
    ({"kind": "this_month"}, (date(2026, 8, 1), THU, "flow")),                             # ngày 1 tới hết hôm nay
    ({"kind": "last_month"}, (date(2026, 7, 1), date(2026, 7, 31), "flow")),
    ({"kind": "ytd"}, (date(2026, 1, 1), THU, "flow")),                                    # từ đầu năm tới hết hôm nay
    ({"kind": "month", "month": 10}, (date(2025, 10, 1), date(2025, 10, 31), "flow")),     # tháng sau hôm nay: năm trước
    ({"kind": "quarter", "quarter": 2}, (date(2026, 4, 1), date(2026, 6, 30), "flow")),
    ({"kind": "until", "date": "2026-08-19"}, (DATA_START, date(2026, 8, 19), "stock")),   # đến hết ngày X: tình trạng
    ({"kind": "next_n_days", "n": 120}, (THU, date(2026, 12, 25), "flow")),                # hết hạn trong N ngày tới
])
def test_section_2_rows(period, expected):
    assert span(period) == expected


def test_a_period_after_today_has_no_answer():
    assert span({"kind": "month", "year": 2026, "month": 9}) is None


def test_this_month_against_last_month_takes_the_same_days():
    june_feb = span({"kind": "this_month"}, date(2026, 3, 31), compare={"kind": "previous_same_days"})
    assert june_feb[1] == (date(2026, 2, 1), date(2026, 2, 28))  # Feb has no 31st: to the end of February
    aug = span({"kind": "this_month"}, THU, compare={"kind": "previous"})
    assert aug[1] == (date(2026, 7, 1), date(2026, 7, 27))


@pytest.mark.parametrize("period,compare,expected", [
    ({"kind": "month", "year": 2026, "month": 2}, "previous", (date(2026, 1, 1), date(2026, 1, 31))),
    ({"kind": "quarter", "year": 2026, "quarter": 1}, "previous", (date(2025, 10, 1), date(2025, 12, 31))),
    ({"kind": "last_week"}, "previous", (date(2026, 8, 10), date(2026, 8, 16))),
    ({"kind": "yesterday"}, "previous", (date(2026, 8, 25), date(2026, 8, 25))),
    ({"kind": "last_n_days", "n": 30}, "previous", (date(2026, 6, 29), date(2026, 7, 28))),  # 30 ngày trước 29/07–27/08
    ({"kind": "month", "year": 2026, "month": 5}, "same_period_last_year", (date(2025, 5, 1), date(2025, 5, 31))),
    ({"kind": "days_from", "date": "2026-03-24", "n": 7}, "before_days_from", (date(2026, 3, 17), date(2026, 3, 23))),
])
def test_compare_periods(period, compare, expected):
    assert span(period, compare={"kind": compare})[1] == expected


def test_kinds_without_a_single_previous_period_abstain():
    assert span({"kind": "ytd"}, compare={"kind": "previous"}) is None


def test_stock_metrics_are_a_state_whatever_the_period_says():
    assert span({"kind": "today"}, metric="stock_qty") == (DATA_START, THU, "stock")  # "tồn cuối ngày hôm nay"
    plan = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "debt_total"}]})
    r = resolve(plan, THU, CAL)
    assert (r.period.start, r.period.end, r.period.mode) == (DATA_START, THU, "stock")


def test_months_series():
    plan = QueryPlan.model_validate({"intent": "trend", "measures": [{"metric": "revenue"}],
                                     "period": {"kind": "months", "end": "2026-06", "n": 3}})
    r = resolve(plan, THU, CAL)
    assert [(s.start, s.end) for s in r.series] == [(date(2026, 4, 1), date(2026, 4, 30)),
                                                     (date(2026, 5, 1), date(2026, 5, 31)),
                                                     (date(2026, 6, 1), date(2026, 6, 30))]


@pytest.mark.skipif(not CAL.exists(), reason="cần data/train/calendar.csv")
def test_tet_from_23_chap_to_10_gieng_and_before_tet():
    assert tet_window(2026, CAL) == (date(2026, 2, 10), date(2026, 2, 26))
    tet, before = span({"kind": "tet", "lunar_year": 2026}, date(2026, 9, 14), compare={"kind": "before_tet", "n": 17})
    assert tet[:2] == (date(2026, 2, 10), date(2026, 2, 26)) and before == (date(2026, 1, 24), date(2026, 2, 9))
    assert span({"kind": "tet"}, date(2026, 5, 25), compare={"kind": "same_period_last_year"})[1] == tet_window(2025, CAL)
    assert span({"kind": "tet", "lunar_year": 2026}, date(2026, 9, 14), compare={"kind": "before_tet", "n": 18}) is None
