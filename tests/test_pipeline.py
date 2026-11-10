"""End-to-end pipeline on a small fake split and, when present, on the real splits."""
import json
from pathlib import Path

import pytest

from datamate import nlu, pipeline
from datamate.eval.scorer import read_jsonl
from datamate.eval.validate import validate
from datamate.pipeline import RunConfig, find_split_dir, run

DATA = Path(__file__).resolve().parents[1] / "data"


def fake_split(root: Path) -> Path:
    split = root / "fake_split"
    for biz in ("shop_a", "shop_b"):
        (split / "data" / biz).mkdir(parents=True)
        (split / "data" / biz / "README.md").write_text(f"# {biz}", encoding="utf-8")
    (split / "rulebook.md").write_text("## 1. Đơn\n| Luật | Mặc định |\n|---|---|\n| Số đơn | x |\n", encoding="utf-8")
    (split / "calendar.csv").write_text("date,weekday\n2026-01-01,4\n", encoding="utf-8")
    qs = [{"id": "q1", "business_id": "shop_a", "question": "doanh thu hôm nay", "as_of_date": "2026-01-01"},
          {"id": "q2", "business_id": "shop_b", "question": "số đơn hôm qua", "as_of_date": "2026-01-01"},
          {"id": "q3", "business_id": "shop_a", "question": "top 3 món", "as_of_date": "2026-01-01"}]
    (split / "questions.jsonl").write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in qs), encoding="utf-8")
    return split


def lines(out: Path) -> list[dict]:
    return [json.loads(l) for l in (out / "submission.jsonl").read_text(encoding="utf-8").splitlines()]


def test_run_writes_one_line_per_question_and_logs(tmp_path):
    split = fake_split(tmp_path)
    s = run(split, tmp_path / "out")
    assert s.n_questions == 3 and s.types["abstain"] == 3 and s.errors == 0
    assert sorted(l["id"] for l in lines(tmp_path / "out")) == ["q1", "q2", "q3"]
    logs = {p.name for p in (tmp_path / "out" / "logs").iterdir()}
    assert {"q1.json", "q2.json", "q3.json", "_business_shop_a.json"} <= logs


def test_data_folder_may_be_the_parent_of_the_split(tmp_path):
    split = fake_split(tmp_path)
    assert find_split_dir(tmp_path) == split
    run(tmp_path, tmp_path / "out")
    assert len(lines(tmp_path / "out")) == 3


def test_time_budget_exhausted_still_writes_every_line(tmp_path):
    split = fake_split(tmp_path)
    s = run(split, tmp_path / "out", RunConfig(time_budget_s=0, reserve_s=0))
    assert s.timed_out == 3 and len(lines(tmp_path / "out")) == 3
    log = json.loads((tmp_path / "out" / "logs" / "q1.json").read_text(encoding="utf-8"))
    assert "hết thời gian" in log["decision"]


def test_a_crashing_block_only_abstains_that_question(tmp_path, monkeypatch):
    split = fake_split(tmp_path)

    def boom(question, *a, **k):
        if "hôm qua" in question:
            raise RuntimeError("lỗi giả")
        return None
    monkeypatch.setattr(nlu, "parse_question", boom)
    s = run(split, tmp_path / "out")
    assert s.errors == 1 and len(lines(tmp_path / "out")) == 3
    assert "lỗi giả" in json.loads((tmp_path / "out" / "logs" / "q2.json").read_text(encoding="utf-8"))["error"]


def test_business_id_cannot_escape_the_data_folder(tmp_path):
    split = fake_split(tmp_path)
    with pytest.raises(ValueError):
        pipeline.business_dir(split, "../../etc")


@pytest.mark.slow
@pytest.mark.skipif(not (DATA / "public_test" / "questions.jsonl").exists(), reason="cần data/")
def test_real_public_split_gives_a_valid_file(tmp_path):
    run(DATA / "public_test", tmp_path / "out", RunConfig(write_logs=False))
    pred, warnings = read_jsonl(tmp_path / "out" / "submission.jsonl")
    questions, _ = read_jsonl(DATA / "public_test" / "questions.jsonl")
    errors, _, _ = validate(pred, [q["id"] for q in questions])
    assert not warnings and not errors and len(pred) == len(questions)


def test_logs_follow_the_docker_guideline(tmp_path):
    """Guideline 2026 §3.3: one record per question on one line (its own file and logs/questions.jsonl) with id,
    answer, elapsed_ms (a non-negative integer) and thinking (null: thinking is off); code / output null when no
    function answered."""
    split = fake_split(tmp_path)
    run(split, tmp_path / "out")
    logs = tmp_path / "out" / "logs"
    records = [json.loads(l) for l in (logs / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(r["id"] for r in records) == ["q1", "q2", "q3"]
    for r in records:
        assert {"id", "answer", "elapsed_ms", "thinking", "code", "output"} <= set(r)
        assert isinstance(r["elapsed_ms"], int) and r["elapsed_ms"] >= 0 and r["thinking"] is None
    assert len((logs / "q1.json").read_text(encoding="utf-8").strip().splitlines()) == 1
    first = next(r for r in records if r["id"] == "q1")
    assert "business_prep_ms" in first  # the shop's files are read before its first question


def test_a_computed_answer_logs_its_function_inputs_and_output():
    from types import SimpleNamespace
    from datamate.contracts import ExecResult
    log = {"result": ExecResult(value=42, answer_type="number", source="D1", function="sales.value_of"),
           "resolved": {"period": {"start": "2026-01-01"}}}
    got = pipeline.audit_fields(log, SimpleNamespace(raw=SimpleNamespace(root=Path("/data/data/shop_a"))))
    assert got["code"] == "datamate/metrics/sales.py::value_of" and got["output"] == 42 and got["thinking"] is None
    assert got["inputs"]["plan"] == {"period": {"start": "2026-01-01"}}


# ---- N165: whatever is odd about the data folder, a line per question; a second process keeps written answers
def _questions(split: Path) -> list[dict]:
    return [json.loads(l) for l in (split / "questions.jsonl").read_text(encoding="utf-8").splitlines()]


def test_split_two_levels_down(tmp_path):
    split = fake_split(tmp_path / "x")
    deep = tmp_path / "a" / "b" / "c"
    deep.parent.mkdir(parents=True)
    split.rename(deep)
    assert find_split_dir(tmp_path / "a") == deep
    run(tmp_path / "a", tmp_path / "out")
    assert len(lines(tmp_path / "out")) == 3


def test_two_splits_takes_the_shallowest_then_first(tmp_path):
    fake_split(tmp_path / "z")
    deeper = fake_split(tmp_path / "m" / "n")
    only = tmp_path / "a"
    only.mkdir()
    fake_split(only)
    assert find_split_dir(tmp_path) == only / "fake_split"  # depth 2 before depth 3, then by name
    run(tmp_path, tmp_path / "out")
    assert len(lines(tmp_path / "out")) == 3 and deeper.exists()


def test_questions_json_name_and_array(tmp_path):
    split = fake_split(tmp_path)
    qs = _questions(split)
    (split / "questions.jsonl").unlink()
    (split / "Questions.JSON").write_text(json.dumps(qs), encoding="utf-8")
    run(split, tmp_path / "out")
    assert sorted(l["id"] for l in lines(tmp_path / "out")) == ["q1", "q2", "q3"]


def test_questions_utf16(tmp_path):
    split = fake_split(tmp_path)
    text = (split / "questions.jsonl").read_text(encoding="utf-8")
    (split / "questions.jsonl").write_bytes(text.encode("utf-16"))
    run(split, tmp_path / "out")
    assert sorted(l["id"] for l in lines(tmp_path / "out")) == ["q1", "q2", "q3"]


def test_no_questions_anywhere_leaves_an_empty_file(tmp_path):
    (tmp_path / "empty").mkdir()
    s = run(tmp_path / "empty", tmp_path / "out")
    assert s.n_questions == 0 and (tmp_path / "out" / "submission.jsonl").read_text(encoding="utf-8") == ""
    assert (tmp_path / "out" / "logs" / "_run_error.json").exists()


def test_integer_id_gets_a_line(tmp_path):
    split = fake_split(tmp_path)
    (split / "questions.jsonl").write_text(json.dumps(
        {"id": 12345, "business_id": "shop_a", "question": "doanh thu", "as_of_date": "2026-01-01"}), encoding="utf-8")
    run(split, tmp_path / "out")
    assert [l["id"] for l in lines(tmp_path / "out")] == ["12345"]


def test_business_folder_found_whatever_the_case_or_spaces(tmp_path):
    split = fake_split(tmp_path)
    assert pipeline.business_dir(split, " SHOP_A ") == (split / "data" / "shop_a").resolve()
    assert pipeline.business_dir(split, "shop_a") == (split / "data" / "shop_a").resolve()
    with pytest.raises(ValueError):
        pipeline.business_dir(split, "../shop_a")


def test_resume_keeps_answers_and_fills_the_rest(tmp_path):
    split = fake_split(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    keep = {"id": "q1", "type": "unanswerable", "reason": "đã trả lời"}
    (out / "submission.jsonl").write_text(
        json.dumps(keep, ensure_ascii=False) + "\n" + json.dumps({"id": "q2", "type": "abstain"}) + "\nnot json\n",
        encoding="utf-8")
    run(split, out, RunConfig(resume=True))
    got = {l["id"]: l for l in lines(out)}
    assert sorted(got) == ["q1", "q2", "q3"] and got["q1"] == keep and len(lines(out)) == 3
    ids = [json.loads(l)["id"] for l in (out / "logs" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(ids) == ["q2", "q3"]  # q1 keeps its earlier record, the abstain q2 is logged once again
    run(split, out)  # a fresh run: logs restart, one record per id
    ids = [json.loads(l)["id"] for l in (out / "logs" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(ids) == ["q1", "q2", "q3"]
