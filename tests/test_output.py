"""Submission writer, per-question logs and the time guard."""
import json

from datamate.contracts import Decision, SubmissionLine
from datamate.output import SubmissionWriter, TimeGuard, write_log


def test_writer_flushes_each_line_and_keeps_first_answer(tmp_path):
    path = tmp_path / "out" / "submission.jsonl"
    with SubmissionWriter(path) as w:
        assert w.write(SubmissionLine(id="a", type="number", answer=5))
        # readable before close: a run killed now keeps this line
        assert json.loads(path.read_text(encoding="utf-8").splitlines()[0]) == {"id": "a", "type": "number", "answer": 5}
        assert not w.write(SubmissionLine.abstain("a"))
        w.write(SubmissionLine.abstain("b"))
    assert [json.loads(l)["id"] for l in path.read_text(encoding="utf-8").splitlines()] == ["a", "b"]


def test_write_log_serialises_models(tmp_path):
    p = write_log(tmp_path, "q/1", {"decision": Decision(kind="abstain", reason="x"), "elapsed_ms": 3})
    assert p.name == "q_1.json"
    assert json.loads(p.read_text(encoding="utf-8"))["decision"]["kind"] == "abstain"


def test_time_guard():
    assert TimeGuard(0, 0).expired()
    g = TimeGuard(3600, 60)
    assert not g.expired() and 3539 < g.remaining() <= 3600
