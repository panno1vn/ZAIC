"""§3 terms of the public rulebook (H4), and the rule ids every new figure cites: each must be one pipeline.rule_ids
checks against the split's rulebook, or [V] reads it as a missing rule and the answer abstains (06/11: four of them
were not, caught before any run)."""
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from datamate import metrics, pipeline, rules
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan
from datamate.formatter import format_value
from datamate.nlu import link_entities

JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))
PUBLIC = Path(__file__).resolve().parents[1] / "data" / "public_test" / "rulebook.md"


def shop() -> CanonicalDB:
    """K1: 3 orders of 100 000 (9h, 9h, 15h); K2: 1 order of 900 000 (9h) and 2 cancelled; K3: 3 orders of 50 000."""
    rows = [("o1", 9, "K1", "completed", "A", 100_000), ("o2", 9, "K1", "completed", "B", 100_000),
            ("o3", 15, "K1", "completed", "A", 100_000), ("o4", 9, "K2", "completed", "A", 900_000),
            ("o5", 10, "K2", "cancelled", "A", 10_000), ("o6", 11, "K2", "cancelled", "B", 10_000),
            ("o7", 9, "K3", "completed", "C", 50_000), ("o8", 16, "K3", "completed", "C", 50_000),
            ("o9", 17, "K3", "completed", "B", 50_000)]
    o = pd.DataFrame({"order_id": [r[0] for r in rows], "order_time": [datetime(2026, 6, 2, r[1]) for r in rows],
                      "customer_key": [r[2] for r in rows], "status": [r[3] for r in rows], "has_time": True})
    lines = pd.DataFrame({"order_id": [r[0] for r in rows], "product_key": [r[4] for r in rows],
                          "product_name": [r[4] for r in rows], "line_amount": [float(r[5]) for r in rows],
                          "qty": 1.0, "base_qty": 1.0, "is_item": True})
    return CanonicalDB(tables={"orders": o, "lines": lines})


def execute(db, raw):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"period": {"kind": "this_month"}, **raw}),
                        as_of=date(2026, 6, 30), period=JUNE)
    return metrics.execute(link_entities(plan, db), db)


def rank(by, entity, **kw):
    return {"intent": "rank", "rank": {"entity": entity, "by": by, "k": 1, **kw}}


def test_the_terms_of_section_3():
    """Sộp: the highest average order among customers with ≥ 3 orders (K2's 900 000 has 1 order, so K1 at 100 000).
    Đổi ý: most cancelled orders (K2). Ưa chuộng: in most orders (A: 4 orders). Giờ cao điểm: 9h (4 orders)."""
    value = lambda raw: format_value((r := execute(shop(), raw)).answer_type, r.value)  # noqa: E731
    assert value(rank("avg_order_value", "customer", min_orders=3)) == "K1"
    assert value(rank("avg_order_value", "customer")) == "K2"
    assert value(rank("cancel_count", "customer")) == "K2"
    assert value(rank("order_presence", "product")) == "A"
    assert value(rank("order_count", "hour")) == 9


PLANS = [rank("avg_order_value", "customer", min_orders=3), rank("cancel_count", "customer"),
         rank("order_presence", "product"), rank("order_count", "hour"), rank("days_with_purchase", "customer"),
         {"intent": "value", "measures": [{"metric": "order_count", "filters": [{"field": "weekday", "value": "tue"}],
                                           "aggregate": "avg_per_weekday"}]}]


@pytest.mark.skipif(not PUBLIC.exists(), reason="public rulebook not present")
@pytest.mark.parametrize("raw", PLANS)
def test_every_rule_a_new_figure_cites_is_checked_and_holds_in_the_public_rulebook(raw):
    r = execute(shop(), raw)
    assert r is not None
    known = set(pipeline.rule_ids())
    assert set(r.rule_ids) <= known, set(r.rule_ids) - known
    status = rules.check_rules(PUBLIC.read_text(encoding="utf-8-sig"), tuple(r.rule_ids))
    assert all(status.values()), [k for k, v in status.items() if not v]


@pytest.mark.skipif(not PUBLIC.exists(), reason="public rulebook not present")
def test_the_repair_figures_cite_checked_rules():
    from test_repair_jobs import run as _  # noqa: F401  (same tiny ledger)
    from test_repair_jobs import shop as repair
    plans = [{"intent": "value", "measures": [{"metric": "ticket_count", "filters": [
                 {"field": "service", "value": "thay nhớt"}]}]},
             {"intent": "value", "measures": [{"metric": "vehicle_count", "filters": [
                 {"field": "vehicle_model", "value": "Air Blade"}]}]},
             {"intent": "rank", "rank": {"entity": "vehicle_model", "by": "revenue", "k": 1}},
             {"intent": "count_where", "threshold": {"entity": "vehicle", "metric": "ticket_count", "op": "gte",
                                                     "value": 2}}]
    known = set(pipeline.rule_ids())
    rulebook = PUBLIC.read_text(encoding="utf-8-sig")
    for raw in plans:
        r = execute(repair(), raw)
        assert r is not None, raw
        assert set(r.rule_ids) <= known, set(r.rule_ids) - known
        assert all(rules.check_rules(rulebook, tuple(r.rule_ids)).values()), raw
