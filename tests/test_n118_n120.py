"""N118: a "product" that is an active ingredient ("thuốc hoạt chất X") filters by the ingredient; N119: function words
typed with telex left on ("cuwar", "dduwowcj") are no filter value; N120: a revenue reading of a question that counts in
a unit and names no money is a quantity in that unit."""
from datetime import date

import pandas as pd

from datamate import nlu
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.nlu import drop_generic_filters, product_as_attribute

AS_OF = date(2026, 6, 30)


def _resolved(raw: dict) -> ResolvedPlan:
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=AS_OF, linked={},
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=AS_OF, mode="flow"))


def _revenue(field: str, value: str) -> dict:
    return {"intent": "value", "period": {"kind": "this_month"},
            "measures": [{"metric": "revenue", "filters": [{"field": field, "value": value}]}]}


def pharmacy() -> CanonicalDB:
    products = pd.DataFrame({"product_key": ["SP1", "SP2"], "product_name": ["Panadol 500mg", "Betadine 20ml"],
                             "active_ingredient": ["Paracetamol", "Povidon iod"]})
    lines = pd.DataFrame({"order_id": ["1"], "product_key": ["SP1"], "product_name": ["Panadol 500mg"]})
    return CanonicalDB(tables={"products": products, "lines": lines})


def test_an_active_ingredient_written_as_the_product_filters_by_the_ingredient():
    db = pharmacy()
    for value, want in (("Paracetamol", "Paracetamol"), ("thuốc hoạt chất Povidon iod", "povidon iod"),
                        ("thuoc co hoat chat Paracetamol", "paracetamol")):
        f = product_as_attribute(_resolved(_revenue("product", value)), db).plan.measures[0].filters[0]
        assert (f.field, f.value) == ("active_ingredient", want), value
    # a real product stays a product
    f = product_as_attribute(_resolved(_revenue("product", "Panadol 500mg")), db).plan.measures[0].filters[0]
    assert f.field == "product"


def test_a_telex_function_word_is_no_filter_value():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"], "channel": ["Tại quầy"]})})
    for field, value in (("channel", "cuwar"), ("payment_method", "dduwowcj")):
        plan = drop_generic_filters(_resolved(_revenue(field, value)), db)
        assert plan.plan.measures[0].filters == [], value


def test_a_question_that_counts_in_a_unit_is_a_quantity():
    raw = _revenue("product", "cơm chiên dương châu")
    kept, problems = nlu.plan_problems("tháng 5 năm 2026 cửa hàng bán được mấy đĩa cơm chiên dương châu z",
                                       QueryPlan.model_validate(raw), AS_OF)
    assert not problems and kept.measures[0].metric == "quantity" and kept.measures[0].unit == "đĩa"
    # money named: revenue stays
    kept, _ = nlu.plan_problems("tháng 5/2026 bán cơm chiên dương châu được bao nhiêu tiền",
                                QueryPlan.model_validate(raw), AS_OF)
    assert kept.measures[0].metric == "revenue"
