"""H16: a one-measure answer that its measure's definition rules out (a negative count or amount, a rate or share
outside 0–100 %) is not sane; profits, stock, changes between periods and several measures are left alone."""
from datamate.contracts import QueryPlan
from datamate.verify import impossible


def _plan(metric, intent="value", **extra):
    body = {"intent": intent, "measures": [{"metric": metric}], "period": {"kind": "month", "year": 2026, "month": 5}}
    return QueryPlan.model_validate({**body, **extra})


def test_negative_counts_and_amounts():
    assert impossible(_plan("revenue"), -5000)
    assert impossible(_plan("order_count"), -1)
    assert impossible(_plan("quantity"), [2, -3])  # unit split
    assert impossible(_plan("revenue"), 0) is None
    assert impossible(_plan("revenue"), 1_250_000) is None


def test_signed_figures_left_alone():
    assert impossible(_plan("gross_profit"), -200_000) is None
    assert impossible(_plan("net_profit"), -1) is None
    assert impossible(_plan("stock_qty"), -3) is None
    assert impossible(_plan("purchase_minus_sales"), -12) is None


def test_rates_and_shares():
    assert impossible(_plan("cancel_rate"), 140.0)
    assert impossible(_plan("cancel_rate"), 12.5) is None
    share = _plan("revenue", "share", share_of={"metric": "revenue"})
    assert impossible(share, 101.0)
    assert impossible(share, 5.27) is None


def test_compare_and_several_measures_left_alone():
    two = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue"}, {"metric": "order_count"}],
                                    "period": {"kind": "month", "year": 2026, "month": 5}})
    assert impossible(two, [-1, -2]) is None
    assert impossible(_plan("revenue", "compare", compare={"kind": "previous", "output": "diff"}), -300_000) is None
