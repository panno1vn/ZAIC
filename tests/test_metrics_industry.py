"""Industry rules (§6, v2) on a tiny shop built by hand; each expected figure is worked out by hand from the rulebook
row the test names."""
from datetime import date, datetime

import pandas as pd

from datamate import metrics
from datamate.contracts import CanonicalDB, QueryPlan, ResolvedPeriod, ResolvedPlan

JUNE = ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30))


def shop(cancelled: bool = False) -> CanonicalDB:
    orders = pd.DataFrame({"order_id": ["o1", "o2"], "order_time": [datetime(2026, 5, 30), datetime(2026, 6, 2)],
                           "status": ["completed", "cancelled" if cancelled else "returned"]})
    deliveries = pd.DataFrame([
        ("o1", datetime(2026, 5, 31), 1),   # May
        ("o1", datetime(2026, 6, 3), 2),    # one batch written as two rows (two products)
        ("o1", datetime(2026, 6, 3), 2),
        ("o2", datetime(2026, 6, 4), 1),    # an order returned later: its batch counts
        ("o2", datetime(2026, 6, 9), 2),
    ], columns=["order_id", "delivery_time", "batch_no"])
    return CanonicalDB(tables={"orders": orders, "deliveries": deliveries})


def batches(db):
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "delivery_count"}],
                                                       "period": {"kind": "this_month"}}),
                        as_of=date(2026, 6, 30), period=JUNE)
    r = metrics.execute(plan, db)
    return None if r is None else r.value


def test_delivery_batches_of_the_period_each_once_returned_orders_included():
    assert batches(shop()) == 3  # §6: o1 batch 2, o2 batches 1 and 2; o1 batch 1 is May
    assert batches(shop(cancelled=True)) is None  # a cancelled order's batch: no rule
