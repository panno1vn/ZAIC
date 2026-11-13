"""N197: "the shop does not record X" (§7, verify.not_recorded) answers "unanswerable" only for a plan the library has
a function for. Synth 12/11, a spa shop that keeps no debts: "Khách X còn mấy buổi của Gói Y tính đến hôm nay?" was
read as the debt of customer X with a product filter, which no debt function takes; the README never writes "nợ", so
the run answered "unanswerable: không ghi công nợ" (wrong: 3 sessions) where it had no reading to conclude from."""
from datetime import date

import pandas as pd

from datamate import decide
from datamate.contracts import CanonicalDB, CheckResult, ColumnMap, Mapping, QueryPlan, ResolvedPlan, TableMap
from datamate.verify import R_OUTSIDE, collect_signals, not_recorded, plan_taken

README = "# Dữ liệu\n\n## Cột trong `ban.csv`\n- **Mã đơn**: mã đơn\n- **Khách**: tên khách\n- **Hàng**: tên hàng\n"
RULES = {r: True for r in R_OUTSIDE}
MAPPING = Mapping(tables=[TableMap(target="orders", sources=["ban.csv"], columns=[
    ColumnMap(target="order_id", source="Mã đơn"), ColumnMap(target="goods_amount", source="Tiền", parse="money")])],
    checks=[CheckResult(name="ok", passed=True)])


def _db() -> CanonicalDB:
    orders = pd.DataFrame({"order_id": ["D1"], "customer_key": ["Trịnh Văn Trang"], "goods_amount": [1.0]})
    return CanonicalDB(tables={"orders": orders}, readme=README)


def _plan(measure: dict, linked: dict | None = None) -> ResolvedPlan:
    plan = QueryPlan.model_validate({"intent": "value", "period": {"kind": "today"}, "measures": [measure]})
    return ResolvedPlan(plan=plan, as_of=date(2026, 8, 27), linked=linked or {})


SESSIONS = {"metric": "debt_amount", "filters": [{"field": "customer", "value": "Trịnh Văn Trang"},
                                                 {"field": "product", "value": "Gói gội dưỡng sinh 10 buổi"}]}
QUESTION = "Khách Trịnh Văn Trang còn mấy buổi của Gói gội dưỡng sinh 10 buổi tính đến hôm nay?"


def test_a_plan_no_function_takes_is_not_concluded_from():
    plan = _plan(SESSIONS, {"Trịnh Văn Trang": "Trịnh Văn Trang"})
    assert not_recorded(plan.plan, QUESTION, _db()) == "công nợ"  # the README names no debt
    assert not plan_taken(plan)  # a debt takes no product filter
    s = collect_signals(plan, None, _db(), MAPPING, RULES, QUESTION)
    assert not s.out_of_scope and s.subjective is not True
    assert decide.decide(s, None).kind == "abstain"


def test_a_plan_a_function_takes_is_unanswerable_as_before():
    """Train: "3 khách còn nợ nhiều nhất", "khách X còn nợ bao nhiêu" in shops whose README never writes "nợ"."""
    for measure, q in (({"metric": "debt_total", "filters": []}, "Đến hết hôm nay khách còn thiếu bao nhiêu tiền?"),
                       ({"metric": "debt_amount", "filters": [{"field": "customer", "value": "Trịnh Văn Trang"}]},
                        "Khách Trịnh Văn Trang còn nợ bao nhiêu tính đến hôm nay?")):
        plan = _plan(measure)
        assert plan_taken(plan)
        s = collect_signals(plan, None, _db(), MAPPING, RULES, q)
        assert s.out_of_scope and s.subjective is True and "cửa hàng không ghi công nợ (§7)" in s.notes
        assert decide.decide(s, None).kind == "unanswerable"


def test_a_reason_the_shop_does_not_record_needs_no_plan_shape():
    """The reason of a return or a cancellation is read from the question's own words (N112): whatever the plan
    (public: cancel_count with category = "giao trễ", a filter the count does take; or no plan at all)."""
    q = "Th3/2025 có mấy đơn bị huỷ vì giao trễ z?"
    odd = _plan({"metric": "debt_amount", "filters": [{"field": "product", "value": "giao trễ"}]})
    assert not plan_taken(odd)
    for plan in (odd, None):
        s = collect_signals(plan, None, _db(), MAPPING, RULES, q)
        assert s.out_of_scope and s.subjective is True
        assert decide.decide(s, None).kind == "unanswerable"


def test_plan_taken_is_the_test_execute_makes():
    assert plan_taken(_plan({"metric": "revenue", "filters": [{"field": "product_group", "value": "sữa"}]}))
    assert not plan_taken(_plan({"metric": "stock_qty", "filters": [{"field": "customer", "value": "Lan"}]}))
    ranked = QueryPlan.model_validate({"intent": "rank", "period": {"kind": "today"},
                                       "rank": {"entity": "supplier", "by": "quantity", "k": 1, "order": "desc"}})
    assert not plan_taken(ResolvedPlan(plan=ranked, as_of=date(2026, 8, 27)))  # no function ranks suppliers by quantity
