"""N76: a product filter naming one of the shop's units is the unit counted in; "tất cả các món" is no filter."""
from datetime import date

from datamate import nlu
from datamate.contracts import QueryPlan, ResolvedPeriod, ResolvedPlan
from test_metrics_sales import JUNE, shop


def resolved(filters, metric="quantity", unit=None):
    m = {"metric": metric, "filters": filters}
    if unit:
        m["unit"] = unit
    return ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [m],
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=JUNE)


def test_a_unit_of_the_shop_written_as_a_product_is_the_unit():
    r = nlu.unit_or_all_as_product(resolved([{"field": "product", "value": "ly"}]), shop())
    assert r.plan.measures[0].filters == [] and r.plan.measures[0].unit == "ly"


def test_a_real_product_or_a_revenue_keeps_its_filter():
    keep = resolved([{"field": "product", "value": "Bia Tiger lon"}])
    assert nlu.unit_or_all_as_product(keep, shop()).plan.measures[0].filters
    money = resolved([{"field": "product", "value": "ly"}], metric="revenue")
    assert nlu.unit_or_all_as_product(money, shop()).plan.measures[0].filters  # only a quantity counts in a unit


def test_every_product_is_no_filter():
    r = nlu.unit_or_all_as_product(resolved([{"field": "product", "value": "tất cả các món"}]), shop())
    assert r.plan.measures[0].filters == []


def test_every_product_beside_another_measure_is_left_alone():
    """Train 07/11: "mấy ly size M, cộng tất cả các món" read as [size M, every item]: dropping the second filter
    answered a list of two figures where one is asked."""
    two = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "period": {"kind": "this_month"}, "measures": [
        {"metric": "quantity", "filters": [{"field": "size", "value": "M"}]},
        {"metric": "quantity", "filters": [{"field": "product", "value": "tất cả các món"}]}]}),
        as_of=date(2026, 6, 30), period=JUNE)
    # N147: one figure, the every-item measure goes (not a list of two, as dropping its filter alone gave)
    p = nlu.unit_or_all_as_product(two, shop()).plan
    assert len(p.measures) == 1 and p.measures[0].filters[0].field == "size" and p.answer_type == "number"
