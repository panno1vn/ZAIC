"""Regression tests for the second review of the backbone (R15–R20 in docs/HAN_CHE_VA_CAI_THIEN.md §E)."""
import json
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datamate import metrics, pipeline
from datamate.contracts import (CanonicalDB, ColumnMap, Decision, ExecResult, Mapping, QueryPlan, RawBusiness,
                                RawTable, ResolvedPeriod, ResolvedPlan, SubmissionLine, TableMap, format_error)
from datamate.formatter import to_line
from datamate.loader import load_business
from datamate.mapping import build_canonical, run_checks
from datamate.metrics import REGISTRY, metric
from datamate.nlu import baseline
from datamate.output import SubmissionWriter

ANSWER = Decision(kind="answer")


# ---------------------------------------------------------------- R15: numpy values
@pytest.mark.parametrize("value,answer_type,expected", [
    (np.int64(5), "number", 5), ([np.int64(1), np.float64(2.5)], "list", [1, 2.5]), (np.bool_(True), "boolean", True),
    (pd.Timestamp("2026-07-03"), "date", "2026-07-03"), (date(2026, 7, 3), "date", "2026-07-03"),
])
def test_r15_numpy_and_pandas_values_are_written_as_python(value, answer_type, expected):
    line = to_line("q", ANSWER, ExecResult(value=value, answer_type=answer_type, source="D1")).to_dict()
    assert line == {"id": "q", "type": answer_type, "answer": expected}
    json.dumps(line)


def test_r15_an_unwritable_answer_costs_only_that_question(tmp_path, monkeypatch):
    split = tmp_path / "s"
    (split / "data" / "ok").mkdir(parents=True)
    (split / "questions.jsonl").write_text("\n".join(json.dumps({"id": f"q{i}", "business_id": "ok", "question": "x",
                                                                  "as_of_date": "2026-01-01"}) for i in range(3)),
                                           encoding="utf-8")
    real = pipeline.answer_question

    def answer(q, *a, **k):
        if q["id"] == "q0":  # bypasses validation, as a future bug might
            return SubmissionLine.model_construct(id="q0", type="number", answer=float("nan"), reason=None), {}
        return real(q, *a, **k)
    monkeypatch.setattr(pipeline, "answer_question", answer)
    pipeline.run(split, tmp_path / "out")
    lines = [json.loads(l) for l in (tmp_path / "out" / "submission.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [l["id"] for l in lines] == ["q0", "q1", "q2"] and lines[0]["type"] == "abstain"


# ---------------------------------------------------------------- R16: NaN / None inside list and table
@pytest.mark.parametrize("line", [
    {"id": "q", "type": "list", "answer": [float("nan"), 2]},
    {"id": "q", "type": "list", "answer": [None]},
    {"id": "q", "type": "list", "answer": [True]},
    {"id": "q", "type": "table", "answer": {"columns": ["a", "b"], "rows": [["x", None]]}},
    {"id": "q", "type": "table", "answer": {"columns": ["a", "b"], "rows": [["x", float("inf")]]}},
])
def test_r16_lists_and_tables_hold_only_names_and_finite_numbers(line):
    assert format_error(line) is not None
    res = ExecResult(value=line["answer"], answer_type=line["type"], source="D1")
    assert to_line("q", ANSWER, res).type == "abstain"


def test_r16_writer_never_writes_nan(tmp_path):
    with SubmissionWriter(tmp_path / "s.jsonl") as w, pytest.raises(ValueError):
        w.write(SubmissionLine.model_construct(id="q", type="number", answer=float("nan"), reason=None))
    assert (tmp_path / "s.jsonl").read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------- R17: registry
def plan(raw: dict) -> ResolvedPlan:
    return ResolvedPlan(plan=QueryPlan.model_validate(raw), as_of=date(2026, 6, 30),
                        period=ResolvedPeriod(start=date(2026, 6, 1), end=date(2026, 6, 30)))


@pytest.fixture
def registry():
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_r17_rankings_of_different_entities_do_not_replace_each_other(registry):
    day = REGISTRY[("rank", "revenue", "day")].fn

    # an entity the sales library does not rank (T3 registered customer, employee, day, month, product)
    @metric("rank", "revenue", entity="supplier")
    def top_suppliers(p, d):
        return ExecResult(value="Cty Lan", answer_type="string", source="D1")
    assert REGISTRY[("rank", "revenue", "day")].fn is day
    supplier = plan({"intent": "rank", "rank": {"entity": "supplier", "by": "revenue"}, "period": {"kind": "this_month"}})
    assert metrics.execute(supplier, CanonicalDB()).value == "Cty Lan"
    with pytest.raises(ValueError):
        metric("rank", "revenue", entity="supplier")(top_suppliers)
    with pytest.raises(ValueError):  # the library's own key cannot be replaced either
        metric("rank", "revenue", entity="day")(top_suppliers)


def test_r17_a_filter_the_function_does_not_declare_never_reaches_it(registry):
    @metric("value", "cash_collected", filters=("payment_method",))  # a v2 metric: no library function yet
    def paid(p, d):
        return ExecResult(value=3, answer_type="number", source="D1")
    base = {"intent": "value", "period": {"kind": "this_month"}}
    by_method = {"metric": "cash_collected", "filters": [{"field": "payment_method", "value": "COD"}]}
    by_product = {"metric": "cash_collected", "filters": [{"field": "product", "value": "Mì"}]}
    assert metrics.execute(plan({**base, "measures": [by_method]}), CanonicalDB()).value == 3
    assert metrics.execute(plan({**base, "measures": [by_product]}), CanonicalDB()) is None
    compare = {"kind": "filter", "filters": [{"field": "shift", "value": "morning"}]}
    assert metrics.execute(plan({**base, "intent": "compare", "measures": [by_method], "compare": compare}),
                           CanonicalDB()) is None


# ---------------------------------------------------------------- R18: empty required cells
RAW = pd.DataFrame({"Ma": ["A", "B", "C"], "Ngay": ["1 thg 6 2025", "2 thg 6 2025", "ngày ??"],
                    "TT": ["Xong", "Xong", "Xong"], "Hang": ["Mì", "Sữa", "Bia"], "Tien": ["10,000", "8,000", "5,000"]})


def mapping(amount_source: str = "Tien") -> Mapping:
    return Mapping(tables=[
        TableMap(target="orders", sources=["t.csv"], value_maps={"status": {"Xong": "completed"}},
                 columns=[ColumnMap(target="order_id", source="Ma"),
                          ColumnMap(target="order_time", source="Ngay", parse="datetime"),
                          ColumnMap(target="status", source="TT")]),
        TableMap(target="lines", sources=["t.csv"],
                 columns=[ColumnMap(target="order_id", source="Ma"), ColumnMap(target="product_key", source="Hang"),
                          ColumnMap(target="product_name", source="Hang"), ColumnMap(target="qty", const=1.0),
                          ColumnMap(target="line_amount", source=amount_source, parse="money")])])


def checks(frame: pd.DataFrame, m: Mapping) -> dict[str, bool]:
    raw = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="t.csv", file="t.csv", sheet=None, frame=frame)])
    return {c.name: c.passed for c in run_checks(build_canonical(raw, m))}


def test_r18_an_unreadable_date_or_a_missing_amount_column_fails_the_mapping():
    ok = RAW.assign(Ngay=["1 thg 6 2025", "2 thg 6 2025", "3 thg 6 2025"])
    assert all(checks(ok, mapping()).values())
    assert checks(RAW, mapping()) == {**checks(ok, mapping()), "cột bắt buộc đủ giá trị": False}
    assert not checks(ok, mapping("Thanh tien"))["cột bắt buộc đủ giá trị"]


# ---------------------------------------------------------------- R19: sqlite NULL
def test_r19_sqlite_null_is_a_blank_cell_not_the_text_none(tmp_path):
    shop = tmp_path / "shop"
    shop.mkdir()
    con = sqlite3.connect(shop / "pos.sqlite")
    con.execute("create table don_hang (ma text, khach text, tien real)")
    con.executemany("insert into don_hang values (?, ?, ?)", [("A", None, 25000.0), ("B", "Chị Lan", None)])
    con.commit()
    con.close()
    frame = load_business(shop).tables[0].frame
    assert frame["khach"].tolist() == ["", "Chị Lan"] and frame["tien"].tolist() == ["25000", ""]  # integral floats lose .0, so ids stored as REAL still join


# ---------------------------------------------------------------- R20: baseline "which" questions
@pytest.mark.parametrize("question", [
    "doanh thu cao nhat la ngay nao trong thang 7/2026",
    "san pham nao ban duoc nhieu tien nhat thang 6/2026",
    "ngay nao co so don cao nhat thang 6/2026",
    "thang nao doanh thu cao nhat trong quy 2/2026",
])
def test_r20_baseline_does_not_read_a_which_question_as_a_total(question):
    assert baseline.parse(question) is None
