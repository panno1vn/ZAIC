"""Scorer behaviour, one test per rule of rulebook §9 (plus the gold self-check when the data is present)."""
from pathlib import Path

import pytest

from datamate.eval.scorer import (format_error, norm_text, penalized_accuracy, read_jsonl, score_line,
                                  score_submission)

DATA = Path(__file__).resolve().parents[1] / "data" / "train"


def ref(type_, answer, alias=None, id_="q1"):
    return {"id": id_, "type": type_, "answer": answer, "alias": alias or []}


def pred(type_, answer=None, **extra):
    line = {"id": "q1", "type": type_, **extra}
    if answer is not None:
        line["answer"] = answer
    return line


def outcome(p, r):
    return score_line(p, r).outcome


# ---------------------------------------------------------------- number, percent
def test_number_exact_and_float_noise():
    assert outcome(pred("number", 48250000), ref("number", 48250000)) == "correct"
    assert outcome(pred("number", 0.1 + 0.2), ref("number", 0.3)) == "correct"
    assert outcome(pred("number", 48250001), ref("number", 48250000)) == "wrong"


@pytest.mark.parametrize("bad", ["48250000", "4,82 triệu", True, None, [48250000]])
def test_number_wrong_format(bad):
    p = {"id": "q1", "type": "number", "answer": bad}
    assert outcome(p, ref("number", 48250000)) == "wrong"


def test_percent_is_percent_value_two_decimals():
    assert outcome(pred("percent", 12.4), ref("percent", 12.40)) == "correct"
    assert outcome(pred("percent", 0.124), ref("percent", 12.4)) == "wrong"
    assert outcome(pred("percent", 12.41), ref("percent", 12.4)) == "wrong"
    assert outcome(pred("percent", "12,4%"), ref("percent", 12.4)) == "wrong"


def test_type_must_match_reference():
    assert outcome(pred("number", 12.4), ref("percent", 12.4)) == "wrong"


# ---------------------------------------------------------------- date, boolean
def test_date_formats():
    assert outcome(pred("date", "2026-08-15"), ref("date", "2026-08-15")) == "correct"
    assert outcome(pred("date", "2025-09"), ref("date", "2025-09")) == "correct"
    assert outcome(pred("date", "15/08/2026"), ref("date", "2026-08-15")) == "wrong"
    assert outcome(pred("date", "2026-08"), ref("date", "2026-08-15")) == "wrong"
    assert format_error(pred("date", "2026-02-30")) is not None


def test_boolean():
    assert outcome(pred("boolean", True), ref("boolean", True)) == "correct"
    assert outcome(pred("boolean", "có"), ref("boolean", True)) == "wrong"
    assert outcome({"id": "q1", "type": "boolean", "answer": 1}, ref("boolean", True)) == "wrong"


# ---------------------------------------------------------------- string
def test_string_ignores_case_space_punctuation():
    assert outcome(pred("string", "cà phê sữa  m"), ref("string", "Cà phê sữa (M)")) == "correct"
    assert norm_text("Sting dâu 330ml") == norm_text("STING DÂU 330 ML")


def test_string_keeps_diacritics():
    assert outcome(pred("string", "Sting dầu 330ml"), ref("string", "Sting dâu 330ml")) == "wrong"
    assert outcome(pred("string", "Sting dau 330ml"), ref("string", "Sting dâu 330ml")) == "wrong"


def test_string_accepts_alias_and_code():
    r = ref("string", "Costar Omega 3 1000mg lọ 100 viên", ["SP0076", "Costar Omega 3 1000 mg lọ 100 viên"])
    assert outcome(pred("string", "SP0076"), r) == "correct"
    assert outcome(pred("string", "costar omega 3 1000 mg lọ 100 viên"), r) == "correct"


def test_string_in_a_list_is_wrong_format():
    assert outcome(pred("string", ["Sting dâu 330ml"]), ref("string", "Sting dâu 330ml")) == "wrong"


# ---------------------------------------------------------------- list
def test_list_order_matters():
    r = ref("list", ["Cà phê sữa (M)", "Bạc xỉu (M)"], [["SP0003"], ["SP0004"]])
    assert outcome(pred("list", ["Cà phê sữa (M)", "Bạc xỉu (M)"]), r) == "correct"
    assert outcome(pred("list", ["Bạc xỉu (M)", "Cà phê sữa (M)"]), r) == "wrong"
    assert outcome(pred("list", ["SP0003", "bạc xỉu m"]), r) == "correct"
    assert outcome(pred("list", "Cà phê sữa (M), Bạc xỉu (M)"), r) == "wrong"


def test_list_of_numbers_and_single_element():
    assert outcome(pred("list", [3, 10]), ref("list", [3, 10])) == "correct"
    assert outcome(pred("list", [3]), ref("list", [3, 10])) == "wrong"
    assert outcome(pred("list", ["Bạc xỉu"]), ref("list", ["Bạc xỉu"])) == "correct"


# ---------------------------------------------------------------- table
TABLE = {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000], ["Anh Tú", 1500000]]}


def test_table_exact_and_row_order_free():
    r = ref("table", TABLE, [["KH01"], ["KH02"]])
    assert outcome(pred("table", TABLE), r) == "correct"
    shuffled = {"columns": TABLE["columns"], "rows": list(reversed(TABLE["rows"]))}
    assert outcome(pred("table", shuffled), r) == "correct"


def test_table_columns_by_name_then_position():
    r = ref("table", TABLE)
    swapped = {"columns": ["so_tien_no", "khach_hang"], "rows": [[3200000, "Chị Lan"], [1500000, "Anh Tú"]]}
    assert outcome(pred("table", swapped), r) == "correct"
    renamed = {"columns": ["khách", "nợ"], "rows": TABLE["rows"]}
    assert outcome(pred("table", renamed), r) == "correct"


def test_table_values_and_cell_types():
    r = ref("table", TABLE, [["KH01"], ["KH02"]])
    assert outcome(pred("table", {"columns": TABLE["columns"], "rows": [["KH01", 3200000], ["Anh Tú", 1500000]]}), r) == "correct"
    assert outcome(pred("table", {"columns": TABLE["columns"], "rows": [["Chị Lan", 3200001], ["Anh Tú", 1500000]]}), r) == "wrong"
    assert outcome(pred("table", {"columns": TABLE["columns"], "rows": [["Chị Lan", "3.200.000đ"], ["Anh Tú", 1500000]]}), r) == "wrong"
    assert outcome(pred("table", {"columns": TABLE["columns"], "rows": [["Chị Lan", 3200000]]}), r) == "wrong"


# ---------------------------------------------------------------- unanswerable, abstain
def test_unanswerable():
    r = ref("unanswerable", None)
    assert outcome(pred("unanswerable", reason="không có giá vốn"), r) == "correct"
    assert outcome(pred("unanswerable"), r) == "correct"
    assert outcome(pred("number", 0), r) == "wrong"
    assert outcome(pred("unanswerable"), ref("number", 5)) == "wrong"


def test_non_string_reason_counts_as_blank():
    assert outcome(pred("unanswerable", reason=123), ref("unanswerable", None)) == "abstain"


def test_abstain_missing_and_unknown_type():
    assert outcome(pred("abstain"), ref("number", 5)) == "abstain"
    assert outcome(None, ref("number", 5)) == "abstain"
    assert outcome(pred("text", "5"), ref("number", 5)) == "wrong"


# ---------------------------------------------------------------- whole submission
def test_penalized_accuracy_and_duplicates():
    refs = [ref("number", 1, id_="a"), ref("number", 2, id_="b"), ref("number", 3, id_="c")]
    lines = [{"id": "a", "type": "number", "answer": 0}, {"id": "a", "type": "number", "answer": 1},
             {"id": "b", "type": "number", "answer": 9}, {"id": "zzz", "type": "abstain"}]
    verdicts, warnings = score_submission(lines, refs)
    assert [v.outcome for v in verdicts] == ["correct", "wrong", "abstain"]
    assert penalized_accuracy(verdicts) == 0
    assert any("lặp lại" in w for w in warnings) and any("không có trong đáp án" in w for w in warnings)


@pytest.mark.skipif(not (DATA / "answers.jsonl").exists(), reason="cần data/train/answers.jsonl")
def test_gold_scores_perfectly():
    refs, warnings = read_jsonl(DATA / "answers.jsonl")
    verdicts, _ = score_submission(refs, refs)
    assert not warnings and len(verdicts) == 3000
    assert all(v.outcome == "correct" for v in verdicts)
    assert penalized_accuracy(verdicts) == 1.0
