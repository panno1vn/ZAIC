"""Contracts: example plans, schema files, validation rules, and the stub chain that must always abstain."""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from datamate import codegen, decide, formatter, loader, mapping, metrics, nlu, rules, temporal, verify
from datamate.contracts import (CanonicalDB, Compare, Mapping, PeriodExpr, QueryPlan, ResolvedPlan, SubmissionLine,
                                TableMap, check_frame)
from datamate.contracts.export_schema import MODELS, SCHEMA_DIR, render
from datamate.llm import MockLLM

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "assets" / "plans" / "examples_v0.jsonl"
ANSWERS = ROOT / "data" / "train" / "answers.jsonl"


def load_examples():
    return [json.loads(line) for line in EXAMPLES.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- example plans
def test_example_plans_are_valid_and_cover_intents():
    plans = [QueryPlan.model_validate(e["plan"]) for e in load_examples()]
    assert len(plans) >= 20
    assert {p.intent for p in plans} >= {"value", "compare", "share", "rank", "count_where", "trend", "series",
                                         "out_of_scope"}


@pytest.mark.skipif(not ANSWERS.exists(), reason="cần data/train/answers.jsonl")
def test_example_answer_types_match_train_answers():
    ref = {json.loads(l)["id"]: json.loads(l)["type"] for l in ANSWERS.read_text(encoding="utf-8").splitlines()}
    for e in load_examples():
        assert e["plan"]["answer_type"] == ref[e["id"]], e["id"]


def test_schema_files_are_up_to_date():
    for name in MODELS:
        path = SCHEMA_DIR / f"{name}.schema.json"
        assert path.exists() and path.read_text(encoding="utf-8") == render(name), \
            f"chạy lại: python -m datamate.contracts.export_schema ({name})"


# ---------------------------------------------------------------- validation rules
@pytest.mark.parametrize("bad", [
    {"kind": "month"},
    {"kind": "days_from", "date": "2026-02-05"},
    {"kind": "months"},
    {"kind": "range", "start": "2026-01-01"},
    {"kind": "month", "month": 13},
])
def test_period_requires_fields_of_its_kind(bad):
    with pytest.raises(ValidationError):
        PeriodExpr.model_validate(bad)


def test_months_series_by_list_or_end_and_n():
    assert PeriodExpr(kind="months", months=["2025-12", "2026-01"]).months
    assert PeriodExpr(kind="months", end="2025-06", n=3).n == 3


@pytest.mark.parametrize("bad", [
    {"intent": "rank", "measures": [{"metric": "revenue"}], "answer_type": "list"},
    {"intent": "out_of_scope", "answer_type": "unanswerable"},
    {"intent": "trend", "measures": [{"metric": "revenue"}], "period": {"kind": "this_month"}, "answer_type": "boolean"},
    {"intent": "value", "answer_type": "number"},
    {"intent": "value", "measures": [{"metric": "profit_margin"}], "answer_type": "number"},
])
def test_plan_consistency(bad):
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(bad)


def test_price_effect_without_date_uses_anchor_price():  # H2
    p = PeriodExpr(kind="days_from", n=7, anchor_price=3200)
    assert p.date is None and p.anchor_price == 3200
    with pytest.raises(ValidationError):
        PeriodExpr(kind="days_from", n=7)


@pytest.mark.parametrize("bad", [  # H6
    {"kind": "day", "date": "05/02/2026"},
    {"kind": "until", "date": "2026-02-30"},
    {"kind": "range", "start": "1/2026", "end": "2026-03"},
    {"kind": "months", "months": ["2025-3"]},
    {"kind": "months", "end": "2025-06-30", "n": 3},
])
def test_period_date_formats(bad):
    with pytest.raises(ValidationError):
        PeriodExpr.model_validate(bad)


def test_answer_type_is_derived_or_checked():  # H5
    base = {"intent": "rank", "measures": [{"metric": "revenue"}], "period": {"kind": "last_week"}}
    assert QueryPlan.model_validate({**base, "rank": {"entity": "customer", "by": "revenue"}}).answer_type == "string"
    assert QueryPlan.model_validate({**base, "rank": {"entity": "customer", "by": "revenue", "k": 3}}).answer_type == "list"
    assert QueryPlan.model_validate({**base, "rank": {"entity": "day", "by": "revenue"}}).answer_type == "date"
    assert QueryPlan.model_validate({**base, "rank": {"entity": "hour", "by": "revenue"}}).answer_type == "number"
    assert QueryPlan.model_validate({**base, "rank": {"entity": "customer", "by": "revenue", "k": 3,
                                                      "with_values": True}}).answer_type == "table"
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({**base, "rank": {"entity": "customer", "by": "revenue"}, "answer_type": "list"})
    with pytest.raises(ValidationError):  # rank.by disagrees with the measure
        QueryPlan.model_validate({**base, "rank": {"entity": "customer", "by": "order_count"}})
    two = {"intent": "value", "measures": [{"metric": "revenue"}, {"metric": "revenue"}], "period": {"kind": "today"}}
    assert QueryPlan.model_validate(two).answer_type == "list"
    stock = {"intent": "value", "measures": [{"metric": "stock_qty", "unit_split": True}], "period": {"kind": "today"}}
    assert QueryPlan.model_validate(stock).answer_type == "list"


def test_average_per_weekday_and_list_items():  # H4
    p = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue", "aggregate": "avg_per_weekday",
                                  "filters": [{"field": "weekday", "value": "sat"}]}],
                                  "period": {"kind": "month", "year": 2026, "month": 3}})
    assert p.answer_type == "number"
    q = QueryPlan.model_validate({"intent": "list_items", "list_spec": {"entity": "product", "condition": "unsold_in_period"},
                                  "period": {"kind": "this_month"}})
    assert q.answer_type == "list"
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"intent": "list_items", "period": {"kind": "this_month"}})


def test_rulebook_industry_metrics_exist():  # H1: one metric per industry rule of the public rulebook
    from typing import get_args
    from datamate.contracts.plan import FilterField, Metric
    assert set(get_args(Metric)) >= {"work_days", "purchase_minus_sales", "expiring_value", "voucher_discount",
                                      "points_discount", "shipping_fee_total", "ticket_count", "avg_ticket_value",
                                      "vehicle_count", "warranty_rate", "trade_in_amount", "amount_due_total",
                                      "overdue_installment_count"}
    assert set(get_args(FilterField)) >= {"stage", "service", "vehicle_model", "plate", "product_line", "category",
                                          "debt_age_days", "is_warranty"}


def test_mapping_transforms_need_their_args():  # H3
    from datamate.contracts import ColumnMap
    assert ColumnMap(target="size", source="Tên món", transform="regex_extract", args={"pattern": r"\((M|L)\)$"})
    with pytest.raises(ValidationError):
        ColumnMap(target="size", source="Tên món", transform="regex_extract")
    with pytest.raises(ValidationError):
        ColumnMap(target="size", source="Tên món", transform="uppercase")


def test_canonical_has_customer_attributes_and_discount_kinds():  # H7
    from datamate.contracts import TABLES
    assert TABLES["customers"].column("address") and TABLES["customers"].column("gender")
    assert TABLES["orders"].column("voucher_discount") and TABLES["orders"].column("points_discount")
    assert "installments" in TABLES and "warranty_visits" in TABLES


def test_compare_needs_its_payload():
    with pytest.raises(ValidationError):
        Compare(kind="filter")
    with pytest.raises(ValidationError):
        Compare(kind="period")


def test_mapping_rejects_unknown_targets():
    with pytest.raises(ValidationError):
        TableMap(target="sales", sources=["a.csv"], columns=[])
    with pytest.raises(ValidationError):
        TableMap.model_validate({"target": "orders", "sources": ["a.csv"], "columns": [{"target": "revenue"}]})
    assert not Mapping().ok


def test_an_orders_only_shop_with_a_side_table_is_usable():
    """Orders without lines, the goods amount on the orders: usable, whatever side tables come with it (a staff list,
    public repair shop 05/11); the goods amount of another table does not make it so."""
    passed = [{"name": "x", "passed": True}]
    orders = {"target": "orders", "sources": ["a.csv"], "columns": [{"target": "order_id", "source": "id"},
                                                                    {"target": "goods_amount", "source": "tien"}]}
    staff = {"target": "employees", "sources": ["b.csv"], "columns": [{"target": "employee_key", "source": "ten"}]}
    assert Mapping.model_validate({"tables": [orders], "checks": passed}).ok
    assert Mapping.model_validate({"tables": [orders, staff], "checks": passed}).ok
    assert not Mapping.model_validate({"tables": [orders, staff], "checks": [{"name": "x", "passed": False}]}).ok
    no_amount = {**orders, "columns": orders["columns"][:1]}
    assert not Mapping.model_validate({"tables": [no_amount, staff], "checks": passed}).ok


def test_check_frame():
    df = pd.DataFrame({"order_id": ["1"], "status": ["xong"], "foo": [1]})
    problems = check_frame("orders", df)
    assert any("order_time" in p for p in problems)
    assert any("status" in p for p in problems)
    assert any("foo" in p for p in problems)
    assert check_frame("nope", df) == ["bảng chuẩn không tồn tại: nope"]


def test_canonical_db_has():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"], "channel": [None]})})
    assert db.has("orders") and db.has("orders", "order_id")
    assert not db.has("orders", "channel") and not db.has("lines")


def test_submission_line_format():
    assert SubmissionLine(id="q", type="number", answer=5).to_dict() == {"id": "q", "type": "number", "answer": 5}
    assert SubmissionLine(id="q", type="unanswerable", reason="x").to_dict()["reason"] == "x"
    assert SubmissionLine.abstain("q").to_dict() == {"id": "q", "type": "abstain"}
    with pytest.raises(ValidationError):
        SubmissionLine(id="q", type="number", answer="5")
    with pytest.raises(ValidationError):
        SubmissionLine(id="q", type="date", answer="15/08/2026")


# ---------------------------------------------------------------- stubs: the chain runs and abstains
def test_stub_chain_abstains(tmp_path):
    (tmp_path / "README.md").write_text("# shop", encoding="utf-8")
    raw = loader.load_business(tmp_path)
    profile = loader.profile_business(raw)
    m = mapping.map_business(raw, profile, rulebook="")
    db = mapping.build_canonical(raw, m)
    card = mapping.build_card(db)
    assert nlu.parse_question("doanh thu hôm nay", date(2026, 8, 1), card) is not None  # baseline parser
    plan = QueryPlan.model_validate(load_examples()[0]["plan"])
    resolved = temporal.resolve(plan, date(2026, 8, 1), tmp_path / "calendar.csv")
    resolved = nlu.link_entities(resolved, db)
    result = metrics.execute(resolved, db) or codegen.solve("q", resolved, db, "")
    assert result is None
    sig = verify.collect_signals(resolved, result, db, m, rules.check_rules("", ("§1.x",)))
    d = decide.decide(sig, result)
    assert d.kind == "abstain"
    assert formatter.to_line("q1", d, result).to_dict() == {"id": "q1", "type": "abstain"}


def test_mock_llm():
    llm = MockLLM([{"a": 1}])
    assert llm.generate_json([{"role": "user", "content": "x"}], {}) == {"a": 1}
    with pytest.raises(RuntimeError):
        llm.generate_json([], {})


# ---------------------------------------------------------------- v1.1: K2 contract stress test
K2 = ROOT / "assets" / "plans" / "k2_trial.jsonl"


def test_k2_trial_plans_are_valid():
    trial = [json.loads(l) for l in K2.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(trial) >= 99
    for e in trial:
        QueryPlan.model_validate(e["plan"])


@pytest.mark.skipif(not ANSWERS.exists(), reason="cần data/train/answers.jsonl")
def test_k2_trial_answer_types_match_train_answers():
    ref = {json.loads(l)["id"]: json.loads(l)["type"] for l in ANSWERS.read_text(encoding="utf-8").splitlines()}
    for e in (json.loads(l) for l in K2.read_text(encoding="utf-8").splitlines() if l.strip()):
        plan = QueryPlan.model_validate(e["plan"])
        if ref[e["id"]] == "unanswerable" and plan.intent != "out_of_scope":
            continue  # the shop lacks the data: decided by [V]/[E] from the data, not by the plan
        assert plan.answer_type == ref[e["id"]], e["id"]


MAY = {"kind": "month", "year": 2025, "month": 5}


@pytest.mark.parametrize("filt,ok", [
    ({"field": "shift", "value": "morning"}, True), ({"field": "shift", "value": "sáng"}, False),
    ({"field": "prescription", "value": True}, True), ({"field": "prescription", "value": 1.0}, False),
    ({"field": "weekday", "op": "in", "value": ["sat", "sun"]}, True), ({"field": "product", "value": True}, False),
    ({"field": "order_status", "value": "cancelled"}, True), ({"field": "order_status", "value": "huỷ"}, False),
])
def test_coded_filter_values(filt, ok):
    plan = {"intent": "value", "measures": [{"metric": "revenue", "filters": [filt]}], "period": MAY}
    if ok:
        QueryPlan.model_validate(plan)
    else:
        with pytest.raises(ValidationError):
            QueryPlan.model_validate(plan)


def test_list_count_and_count_where_without_measures():
    unsold = {"intent": "list_items", "period": {"kind": "range", "start": "2026-06-20", "end": "2026-06-26"},
              "list_spec": {"entity": "product", "condition": "unsold_in_period", "count": True}}
    assert QueryPlan.model_validate(unsold).answer_type == "number"
    loyal = {"intent": "count_where", "period": MAY,
             "threshold": {"entity": "customer", "metric": "order_count", "op": "gte", "value": 3}}
    assert QueryPlan.model_validate(loyal).answer_type == "number"
    with pytest.raises(ValidationError):  # measures[0] must be the thresholded metric
        QueryPlan.model_validate({**loyal, "measures": [{"metric": "revenue"}]})


def test_expiry_window_as_period_and_tet_without_year():
    expiring = {"intent": "list_items", "list_spec": {"entity": "product", "condition": "expiring_within"}}
    QueryPlan.model_validate({**expiring, "period": {"kind": "range", "start": "2026-05-25", "end": "2026-09-22"}})
    QueryPlan.model_validate({**expiring, "period": {"kind": "next_n_days", "n": 120}})
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({**expiring, "period": {"kind": "this_month"}})
    assert PeriodExpr(kind="tet").lunar_year is None


def test_unknown_fields_reject_the_plan_and_the_mapping():  # a typo must not drop a filter silently
    typo = {"intent": "value", "measures": [{"metric": "revenue", "filter": [{"field": "product", "value": "Coca"}]}],
            "period": MAY}
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(typo)
    with pytest.raises(ValidationError):
        Mapping.model_validate({"tables": [], "record_grian": "order"})
    schema = json.loads((SCHEMA_DIR / "query_plan.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
