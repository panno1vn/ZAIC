"""N137–N142: misreadings the rulebook settles, rewritten instead of refused — a quarter read as its month number,
"hot nhất / best seller" ranked by money, "số đơn / số bill" read as revenue, a warranty flag the question never
asks, "k khách nợ nhiều nhất" read as one debt, "lãi gộp" read as revenue, "lô gần hết hạn nhất … ngày nào"."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan

AS_OF = date(2026, 6, 30)


def _accept(question: str, raw: dict):
    return nlu.accept_plan(question, QueryPlan.model_validate(raw), AS_OF)


def test_a_quarter_read_as_its_month_number_is_the_quarter():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 2},
           "measures": [{"metric": "order_count"}]}
    p = _accept("so don quy 2/2025 la bn", raw)
    assert p is not None and (p.period.kind, p.period.quarter, p.period.year) == ("quarter", 2, 2025)
    # another month than the quarter's number stays refused
    raw["period"]["month"] = 3
    assert _accept("so don quy 2/2025 la bn", raw) is None


def test_hot_and_best_seller_rank_by_quantity():
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 3},
           "rank": {"entity": "product", "by": "revenue", "k": 3}}
    p = _accept("cho toi 3 mon hot nhat trong thang 3/2026", raw)
    assert p is not None and p.rank.by == "quantity" and p.rank.k == 3
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 2},
           "rank": {"entity": "product", "by": "quantity", "k": 5}}
    assert _accept("5 best seller thang 2/2026 la nhung mat hang nao", raw) is not None
    # money named: the revenue ranking stays
    raw = {"intent": "rank", "period": {"kind": "month", "year": 2026, "month": 3},
           "rank": {"entity": "product", "by": "revenue", "k": 3}}
    p = _accept("3 mon hot nhat theo doanh thu thang 3/2026", raw)
    assert p is not None and p.rank.by == "revenue"


def test_the_number_of_orders_is_no_revenue_also_as_a_percent():
    raw = {"intent": "compare", "period": {"kind": "last_week"},
           "measures": [{"metric": "revenue", "filters": [{"field": "shift", "value": "afternoon"}]}],
           "compare": {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}], "output": "pct_change"}}
    p = _accept("xem giúp tuần rồi, số ddown ca chiều tăng hay giảm bao nhiu % so vs ca sáng", raw)
    assert p is not None and p.measures[0].metric == "order_count"
    assert [f.value for f in p.measures[0].filters] == ["afternoon"]
    raw = {"intent": "value", "period": {"kind": "quarter", "year": 2026, "quarter": 2},
           "measures": [{"metric": "revenue", "filters": [{"field": "payment_method", "value": "soos bill"}]}]}
    p = _accept("soos bill quý 2/2026 là bnhiu", raw)
    assert p is not None and p.measures[0].metric == "order_count" and not p.measures[0].filters
    # a money word keeps the revenue
    raw = {"intent": "value", "period": {"kind": "this_month"}, "measures": [{"metric": "revenue"}]}
    p = _accept("tiền của số đơn tháng này là bao nhiêu", raw)
    assert p is not None and p.measures[0].metric == "revenue"


def test_a_warranty_flag_the_question_never_asks_is_dropped():
    raw = {"intent": "compare", "period": {"kind": "month", "year": 2026, "month": 2},
           "measures": [{"metric": "revenue", "filters": [{"field": "is_warranty", "value": True}]}],
           "compare": {"kind": "same_period_last_year", "output": "pct_change"}}
    p = _accept("dthu thang 2/2026 so vs cung ky nam ngoai thay doi bao nhieu %", raw)
    assert p is not None and not p.measures[0].filters
    p = _accept("dthu bảo hành thang 2/2026 so vs cung ky nam ngoai thay doi bao nhieu %", raw)
    assert p is not None and p.measures[0].filters[0].field == "is_warranty"


def test_k_customers_with_the_most_debt_are_a_ranking_with_amounts():
    raw = {"intent": "value", "period": {"kind": "until", "date": "2025-10-27"},
           "measures": [{"metric": "debt_amount", "filters": [{"field": "customer", "value": "top_3", "op": "gte"}]}]}
    p = nlu.accept_plan("tính đến hết ngày 27/10/2025, 3 khách nào đang nợ nhiều nhất, mỗi người còn nợ bao nhiêu",
                        QueryPlan.model_validate(raw), date(2025, 10, 27))
    assert p is not None and p.intent == "rank" and not p.measures
    assert (p.rank.entity, p.rank.by, p.rank.k, p.rank.with_values) == ("customer", "debt_amount", 3, True)


def test_gross_profit_named_is_no_revenue():
    raw = {"intent": "value", "period": {"kind": "month", "year": 2025, "month": 8},
           "measures": [{"metric": "revenue", "filters": [{"field": "product_group", "value": "lai gop"}]}]}
    p = _accept("thang 8/2025 lai gop cua cua hang la bao nhiu", raw)
    assert p is not None and p.measures[0].metric == "gross_profit" and not p.measures[0].filters


def test_the_nearest_expiry_date_of_a_lot_is_no_which_time_question():
    raw = {"intent": "value", "period": {"kind": "until", "date": "2026-06-28"},
           "measures": [{"metric": "nearest_expiry", "filters": [{"field": "product", "value": "Oresol 245"}]}]}
    assert _accept("Tính đến hết ngày 28/06/2026, lô Oresol 245 gần hết hạn nhất có hạn dùng ngày nào?", raw) is not None


def test_measures_told_apart_by_the_warranty_flag_alone_become_one():
    raw = {"intent": "compare", "period": {"kind": "month", "year": 2026, "month": 4},
           "measures": [{"metric": "revenue", "filters": [{"field": "is_warranty", "value": False}]},
                        {"metric": "revenue", "filters": [{"field": "is_warranty", "value": True}]}],
           "compare": {"kind": "same_period_last_year"}}
    p = _accept("Tháng 4/2026 doanh thu so với cùng kỳ năm trước tăng hay giảm mấy %?", raw)
    assert p is not None and len(p.measures) == 1 and not p.measures[0].filters


def test_values_that_name_nothing_are_no_filter_but_a_threshold_stays():
    from datamate.nlu import _generic_value
    for v, field in (("nawm", "product"), ("4/2026", "product"), ("chi", "product"), ("do", "category"),
                     ("dDown", "payment_method"), ("xe ddax", "vehicle_model")):
        assert _generic_value(v, field), v
    assert not _generic_value(">=187", "product") and not _generic_value("≥ 187", "product")
    assert not _generic_value("Đỗ", "customer") and not _generic_value("Nam", "customer")  # names of people
    assert not _generic_value("Bánh croissant", "product")
