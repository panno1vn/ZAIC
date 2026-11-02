"""Walking skeleton (05/11): parsers, baseline question parser, temporal engine, mapping build, sales metrics,
formatter, and the end-to-end oracle run on biz_101."""
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from datamate.contracts import (CanonicalDB, ColumnMap, Decision, ExecResult, Mapping, PeriodExpr, QueryPlan,
                                RawBusiness, RawTable, TableMap)
from datamate.formatter import format_value, money, to_line
from datamate.loader.parse import parse_datetime, parse_money, parse_number
from datamate.mapping import build_canonical, run_checks
from datamate.metrics import execute
from datamate.nlu import baseline
from datamate.temporal import resolve, resolve_period

DATA = Path(__file__).resolve().parents[1] / "data"


# ---------------------------------------------------------------- cell parsers
@pytest.mark.parametrize("raw,expected", [
    ("560,000", 560000), ("30.500đ", 30500), ("-30.500đ", -30500), ("25k", 25000), ("1.048.000", 1048000),
    ("22,000", 22000), ("1,5tr", 1500000), (560000, 560000), ("", None), ("abc", None),
])
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1 thg 6 2025", datetime(2025, 6, 1)), ("01/06/2026", datetime(2026, 6, 1)), ("46023", datetime(2026, 1, 1)),
    (46023, datetime(2026, 1, 1)), ("2026-01-01 14:58:08", datetime(2026, 1, 1, 14, 58, 8)), ("31/02/2026", None),
])
def test_parse_datetime(raw, expected):
    assert parse_datetime(raw) == expected


def test_day_month_without_year_uses_the_sheet_year():
    assert parse_datetime("1/6", year_hint=2026) == datetime(2026, 6, 1)
    assert parse_datetime("1/6") is None
    assert parse_number("5 chai") == 5 and parse_number("1,5") == 1.5


# ---------------------------------------------------------------- baseline parser
@pytest.mark.parametrize("question,intent,metric,kind", [
    ("tong dthu thang 6 nam 2025 la bn", "value", "revenue", "month"),
    ("e so don hang quy 4/2025 la bao nhiu vay", "value", "order_count", "quarter"),
    ("Cho tôi biết số đơn hqua", "value", "order_count", "yesterday"),
    ("Hôm nay cửa hàng bán được bao nhiêu tiền?", "value", "revenue", "today"),
    ("Mặt hàng bán chạy nhất tháng 6 năm 2026 là mặt hàng nào vậy?", "rank", "quantity", "month"),
    ("ê revenue ngày nào cao nhất trong tháng 7 năm 2026", "rank", "revenue", "month"),
])
def test_baseline_recognises_frequent_shapes(question, intent, metric, kind):
    p = baseline.parse(question)
    assert p is not None and p.intent == intent and p.period.kind == kind
    assert (p.rank.by if intent == "rank" else p.measures[0].metric) == metric


@pytest.mark.parametrize("question", [
    "Doanh thu của Coca Cola 330ml trong tháng 5 năm 2026 là bao nhiêu?",   # product filter
    "Tháng 7/2025 mặt hàng Nếp cái hoa vàng bán được tổng cộng bao nhiêu kg?",
    "Giá bán một gói Thuốc lá Vinataba vào ngày 28/07/2025 là bao nhiêu?",
    "doanh thu thang 5/2026 cua nhom nuoc ngot",                            # group filter
    "doanh thu bao nhiêu",                                                  # no period
])
def test_baseline_refuses_what_it_cannot_fully_read(question):
    assert baseline.parse(question) is None


# ---------------------------------------------------------------- temporal engine
def test_month_quarter_today_and_clipping():
    as_of = date(2026, 8, 24)
    p = resolve_period(PeriodExpr(kind="month", year=2026, month=8), as_of)
    assert (p.start, p.end) == (date(2026, 8, 1), date(2026, 8, 24))  # records after today have not happened
    q = resolve_period(PeriodExpr(kind="quarter", quarter=4, year=2025), as_of)
    assert (q.start, q.end) == (date(2025, 10, 1), date(2025, 12, 31))
    assert resolve_period(PeriodExpr(kind="yesterday"), as_of).start == date(2026, 8, 23)
    assert resolve_period(PeriodExpr(kind="month", year=2026, month=9), as_of) is None  # entirely after today


def test_month_without_year_follows_rule_2():
    assert resolve_period(PeriodExpr(kind="month", month=9), date(2026, 8, 24)).start == date(2025, 9, 1)
    assert resolve_period(PeriodExpr(kind="month", month=3), date(2026, 8, 24)).start == date(2026, 3, 1)


def test_unsupported_shapes_resolve_to_none_for_now():
    plan = QueryPlan.model_validate({"intent": "compare", "measures": [{"metric": "revenue"}],
                                     "period": {"kind": "this_month"}, "compare": {"kind": "previous_same_days"}})
    assert resolve(plan, date(2026, 8, 24), Path("x")) is None


# ---------------------------------------------------------------- mapping build + metrics on a tiny shop
RAW = pd.DataFrame({
    "Ma": ["A", "A", "A", "B", "C", "D", "E"],
    "Ngay": ["1 thg 6 2025", "1 thg 6 2025", "1 thg 6 2025", "1 thg 6 2025", "2 thg 6 2025", "2 thg 6 2025", "3 thg 6 2025"],
    "TT": ["Xong", "Xong", "Xong", "Đã hủy", "Đổi trả", "Đang giao", "Xong"],
    "Hang": ["Mì", "Mì", "Sữa", "Mì", "Sữa", "Sữa", "Bia"],
    "SL": ["2", "2", "1", "5", "1", "3", "4"],
    "Tien": ["10,000", "10,000", "8,000", "25,000", "8,000", "24,000", "40,000"],
})
MAPPING = Mapping(tables=[
    TableMap(target="orders", sources=["t.csv"], value_maps={"status": {"Xong": "completed", "Đã hủy": "cancelled",
                                                                      "Đổi trả": "returned", "Đang giao": "delivering"}},
             columns=[ColumnMap(target="order_id", source="Ma"), ColumnMap(target="order_time", source="Ngay", parse="datetime"),
                      ColumnMap(target="status", source="TT")]),
    TableMap(target="lines", sources=["t.csv"],
             columns=[ColumnMap(target="order_id", source="Ma"), ColumnMap(target="product_key", source="Hang"),
                      ColumnMap(target="product_name", source="Hang"), ColumnMap(target="qty", source="SL", parse="qty"),
                      ColumnMap(target="base_qty", source="SL", parse="qty"),
                      ColumnMap(target="line_amount", source="Tien", parse="money")]),
])


def tiny_db() -> CanonicalDB:
    raw = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="t.csv", file="t.csv", sheet=None, frame=RAW)])
    return build_canonical(raw, MAPPING)


def test_build_canonical_dedupes_and_checks_pass():
    db = tiny_db()
    assert len(db.tables["lines"]) == 6  # the duplicated 'Mì' line of order A counts once (§8)
    assert len(db.tables["orders"]) == 5
    assert db.date_ranges["orders"] == (date(2025, 6, 1), date(2025, 6, 3))
    assert all(c.passed for c in run_checks(db))


def test_unmapped_status_fails_the_checks():
    m = MAPPING.model_copy(deep=True)
    m.tables[0].value_maps = {}
    raw = RawBusiness(root=Path("."), readme="", tables=[RawTable(table_id="t.csv", file="t.csv", sheet=None, frame=RAW)])
    assert not all(c.passed for c in run_checks(build_canonical(raw, m)))


def run_plan(plan: dict, as_of=date(2025, 6, 30)):
    return execute(resolve(QueryPlan.model_validate(plan), as_of, Path("x")), tiny_db())


JUNE = {"kind": "month", "year": 2025, "month": 6}


def test_revenue_excludes_cancelled_and_returned_keeps_delivering():
    r = run_plan({"intent": "value", "measures": [{"metric": "revenue"}], "period": JUNE})
    assert r.value == 10000 + 8000 + 24000 + 40000  # A (dedup) + D (đang giao) + E
    assert run_plan({"intent": "value", "measures": [{"metric": "order_count"}], "period": JUNE}).value == 3


def test_rankings():
    top = run_plan({"intent": "rank", "rank": {"entity": "product", "by": "quantity"}, "period": JUNE})
    assert top.value == "Bia"  # Bia 4 = Sữa 1+3 (đơn trả hàng C bị bỏ): hoà, xếp theo mã 'Bia' < 'Sữa' (§9)
    day = run_plan({"intent": "rank", "rank": {"entity": "day", "by": "revenue"}, "period": JUNE})
    assert day.value == "2025-06-03"


def test_filtered_measures_are_left_to_later_work():
    plan = {"intent": "value", "measures": [{"metric": "revenue", "filters": [{"field": "product", "value": "Mì"}]}],
            "period": JUNE}
    assert run_plan(plan) is None


# ---------------------------------------------------------------- formatter
def test_money_and_number_rounding_half_up():
    assert money(2.5) == 3 and money(3.5) == 4 and round(2.5) == 2  # Python's round() would be wrong here
    assert format_value("number", 1234.0) == 1234 and format_value("number", 2.345) == 2.35
    assert format_value("percent", 12.345) == 12.35
    assert format_value("table", {"columns": ["a", "b"], "rows": [["x", 5.0]]}) == {"columns": ["a", "b"], "rows": [["x", 5]]}


def test_to_line_answers_only_when_decided():
    res = ExecResult(value=5.0, answer_type="number", source="D1")
    assert to_line("q", Decision(kind="answer"), res).to_dict() == {"id": "q", "type": "number", "answer": 5}
    assert to_line("q", Decision(kind="abstain"), res).to_dict()["type"] == "abstain"
    bad = ExecResult(value="năm", answer_type="number", source="D1")
    assert to_line("q", Decision(kind="answer"), bad).to_dict()["type"] == "abstain"


# ---------------------------------------------------------------- end to end
@pytest.mark.skipif(not (DATA / "train" / "data" / "biz_101").exists(), reason="cần data/")
def test_oracle_run_on_biz_101_scores_without_wrong_answers(tmp_path):
    from datamate.eval.oracle import oracle_map_fn
    from datamate.eval.scorer import read_jsonl, score_submission
    from datamate.pipeline import RunConfig, run
    run(DATA / "train", tmp_path, RunConfig(write_logs=False, map_fn=oracle_map_fn("train"),
                                           question_filter=lambda q: q["business_id"] == "biz_101"))
    pred, _ = read_jsonl(tmp_path / "submission.jsonl")
    refs = [r for r in read_jsonl(DATA / "train" / "answers.jsonl")[0] if r["id"] in {p["id"] for p in pred}]
    verdicts, _ = score_submission(pred, refs)
    outcomes = [v.outcome for v in verdicts]
    assert outcomes.count("wrong") == 0 and outcomes.count("correct") >= 25
