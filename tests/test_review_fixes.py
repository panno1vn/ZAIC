"""Regression tests for the bugs found in the review of 04/11 (P1–P7 and robustness)."""
import json
from datetime import date
from typing import get_args

import pandas as pd
import pytest
from pydantic import ValidationError

from datamate import metrics, pipeline
from datamate.contracts import (CanonicalDB, CheckResult, ExecResult, ListSpec, Mapping, PeriodExpr, QueryPlan,
                                ResolvedPeriod, ResolvedPlan, TableMap, check_frame)
from datamate.contracts.mapping import TRANSFORMS, Transform
from datamate.metrics import REGISTRY, metric
from datamate.rules import check_rules, parse_rulebook, same_rule
from datamate.verify import collect_signals

SPAN = (date(2025, 1, 1), date(2026, 6, 30))


def world():
    db = CanonicalDB(tables={"orders": pd.DataFrame({"order_id": ["1"]}), "lines": pd.DataFrame({"line_amount": [1.0]})},
                     date_ranges={"orders": SPAN})
    m = Mapping(tables=[TableMap(target="orders", sources=["a"], columns=[]),
                        TableMap(target="lines", sources=["a"], columns=[])],
                checks=[CheckResult(name="x", passed=True)])
    return db, m


def test_p1_lines_take_their_dates_from_orders():
    db, m = world()
    plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "revenue"}],
                                                      "period": {"kind": "month", "year": 2025, "month": 4}}),
                        as_of=date(2026, 6, 30), period=ResolvedPeriod(start=date(2025, 4, 1), end=date(2025, 4, 30)))
    res = ExecResult(value=1, answer_type="number", source="D1", requires=["lines.line_amount"], rule_ids=["r"])
    assert collect_signals(plan, res, db, m, {"r": True}).period_coverage == "full"


def test_p2_share_denominator_filters_must_be_linked():
    db, m = world()
    raw = {"intent": "share", "measures": [{"metric": "quantity", "filters": [{"field": "size", "value": "L"}]}],
           "share_of": {"metric": "quantity", "filters": [{"field": "product_group", "value": "bỉm tã"}]},
           "period": {"kind": "this_month"}}
    plan = ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30))
    assert not collect_signals(plan, None, db, m, {}).entities_ok
    linked = plan.model_copy(update={"linked": {"bỉm tã": "Bỉm tã"}})
    assert collect_signals(linked, None, db, m, {}).entities_ok


def test_p3_rank_without_measures_runs_its_metric():
    db, _ = world()
    saved = dict(REGISTRY)

    @metric("rank", "revenue")
    def top(p, d):
        return ExecResult(value="Khách A", answer_type="string", source="D1")
    try:
        plan = ResolvedPlan(plan=QueryPlan.model_validate({"intent": "rank", "rank": {"entity": "customer", "by": "revenue"},
                                                          "period": {"kind": "last_week"}}), as_of=date(2026, 6, 30))
        assert metrics.execute(plan, db).value == "Khách A"
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_p4_other_metric_states_its_answer_type():
    p = QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "other", "note": "tên nhà cung cấp"}],
                                  "answer_type": "string"})
    assert p.answer_type == "string"
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"intent": "value", "measures": [{"metric": "other"}]})


def test_p5_meaning_flips_count_as_changed_rules():
    rule = "tổng **thành tiền các dòng hàng**. **Không** trừ giảm giá trên cả đơn, **không** cộng thuế VAT"
    assert not same_rule(rule, rule.replace("**Không** trừ", "Trừ"))
    assert not same_rule("trong 30 ngày", "trong 60 ngày")
    assert same_rule(rule, rule.replace("**", ""))


def test_paragraph_ids_survive_an_inserted_paragraph():
    a = "Hôm nay của mỗi câu là as_of_date.\n"
    b = "Đây là một đoạn mới chèn vào đầu.\n" + a
    rid = next(iter(parse_rulebook(a)))
    assert rid in parse_rulebook(b) and check_rules(b, (rid,), {rid: parse_rulebook(a)[rid].text})[rid]


def test_p6_bad_business_or_broken_question_never_stops_the_run(tmp_path):
    split = tmp_path / "s"
    (split / "data" / "ok").mkdir(parents=True)
    rows = [json.dumps({"id": "q1", "business_id": "../x", "question": "a", "as_of_date": "2026-01-01"}),
            "{không phải json",
            json.dumps({"id": "q2", "business_id": "ok", "question": "b", "as_of_date": "2026-01-01"}),
            json.dumps({"id": "q3", "question": "thiếu business_id", "as_of_date": "2026-01-01"})]
    (split / "questions.jsonl").write_text("﻿" + "\n".join(rows), encoding="utf-8")  # with a BOM
    pipeline.run(split, tmp_path / "out")
    ids = [json.loads(l)["id"] for l in (tmp_path / "out" / "submission.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(ids) == ["q1", "q2", "q3"]


def test_p6_unexpected_crash_still_fills_every_line(tmp_path, monkeypatch):
    split = tmp_path / "s"
    (split / "data" / "ok").mkdir(parents=True)
    (split / "questions.jsonl").write_text("\n".join(json.dumps({"id": f"q{i}", "business_id": "ok", "question": "x",
                                                                  "as_of_date": "2026-01-01"}) for i in range(3)),
                                           encoding="utf-8")
    monkeypatch.setattr(pipeline, "answer_question", lambda *a, **k: (_ for _ in ()).throw(MemoryError("giả")))
    with pytest.raises(MemoryError):
        pipeline.run(split, tmp_path / "out")
    assert len((tmp_path / "out" / "submission.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_p7_year_must_be_plausible():
    with pytest.raises(ValidationError):
        PeriodExpr(kind="month", year=25, month=4)
    with pytest.raises(ValidationError):
        ListSpec(entity="product", condition="expiring_within")


def test_transform_names_match_the_literal():
    assert set(TRANSFORMS) == set(get_args(Transform))


def test_check_frame_catches_text_dates_and_numbers():
    df = pd.DataFrame({"order_id": ["1"], "order_time": ["01/06/2026"], "status": ["completed"], "total_due": ["25k"]})
    problems = check_frame("orders", df)
    assert any("order_time" in p for p in problems) and any("total_due" in p for p in problems)
    ok = df.assign(order_time=pd.to_datetime(["2026-06-01"]), total_due=[25000.0])
    assert check_frame("orders", ok) == []
