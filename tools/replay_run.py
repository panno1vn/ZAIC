"""Replay a run from its own logs with today's code, without the LLM: each business is built again from the mapping
the run logged, each question starts from the plan the run logged, and everything after the plan (dates, linking,
metrics, checks, gates, format) is today's code. Prints only counts of what changed, by function and by gate, never a
question or an answer (N22): use it to see what a new gate or fix does to a public run, and to write the file to
submit as a diagnostic.

    python tools/replay_run.py outputs/public_run1 --out outputs/replay/run1_today
    python tools/replay_run.py outputs/public_run1 --out outputs/replay/x --data data/public_test --twin-threshold -1

Exact only when the logs hold every question's plan and every business's mapping (a run with logs on). The twin gate
uses --twin-threshold (default: configs/default.json, as predict does); -1 turns it off.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datamate import nlu, pipeline  # noqa: E402
from datamate.contracts import Mapping, QueryPlan  # noqa: E402
from datamate.output import SubmissionWriter  # noqa: E402
from datamate.predict import DEFAULT_CONFIG, load_config  # noqa: E402


class _NoLLM:
    """Stands for the run's LLM so the twin gate runs as it did; never called (plans and mappings come from logs)."""

    def __getattr__(self, name):
        raise RuntimeError(f"replay: LLM gọi tới ({name}), log thiếu plan hoặc mapping")


def _kind(answer: dict) -> str:
    t = answer.get("type")
    return "trống" if t == "abstain" else "không TLĐ" if t == "unanswerable" else "trả lời"


def _function(log: dict) -> str:
    r = log.get("result")
    return r.get("function", "?") if isinstance(r, dict) else "-"


def replay(run_dir: Path, out_dir: Path, data_dir: Path, twin_threshold: float | None) -> Counter:
    logs = run_dir / "logs"
    split_dir = pipeline.find_split_dir(data_dir)
    rulebook = (split_dir / "rulebook.md").read_text(encoding="utf-8-sig")
    rule_status = pipeline.rules.check_rules(rulebook, pipeline.rule_ids())
    old = {}
    for f in logs.glob("q_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        old[d["id"]] = d
    plans = {qid: d.get("plan") for qid, d in old.items()}
    real_parse = nlu.parse_question
    current: dict = {}

    def logged_plan(question, as_of, card, llm=None, exclude_ids=frozenset()):
        p = plans.get(current["id"])
        return QueryPlan.model_validate(p) if p else None

    nlu.parse_question = logged_plan
    changes: Counter = Counter()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with SubmissionWriter(out_dir / "submission.jsonl") as writer:
            for business_id, qs in pipeline.group_by_business(pipeline.load_questions(split_dir)).items():
                blog = logs / f"_business_{business_id}.json"
                logged = Mapping.model_validate(json.loads(blog.read_text(encoding="utf-8"))["mapping"]) \
                    if blog.exists() else Mapping()
                ctx = pipeline.prepare_business(pipeline.business_dir(split_dir, business_id), rulebook, None,
                                                lambda raw, profile, rb, llm=None, m=logged: m.model_copy(deep=True))
                for q in qs:
                    current["id"] = q["id"]
                    before = old.get(q["id"], {})
                    reader = _NoLLM() if (before.get("reader") or "").startswith("llm") else None
                    line, record = pipeline.answer_question(q, ctx, split_dir / "calendar.csv", rule_status,
                                                            rulebook, reader, twin_threshold)
                    writer.write(line)
                    a, b = before.get("answer", {"type": "abstain"}), line.to_dict()
                    fn = _function(before) if _kind(a) == "trả lời" else (record.get("result").function
                                                                          if record.get("result") else "-")
                    if a == b:
                        changes[("giữ nguyên", _kind(a), fn)] += 1
                    elif _kind(a) == _kind(b):
                        changes[("đổi giá trị", "", fn)] += 1
                    else:
                        reason = record["decision"].reason if _kind(b) != "trả lời" and record.get("decision") else ""
                        changes[(f"{_kind(a)} → {_kind(b)}", reason[:60], fn)] += 1
                    if "error" in record:
                        changes[("lỗi khi chạy lại", "", fn)] += 1
    finally:
        nlu.parse_question = real_parse
    return changes


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="thư mục của lượt chạy cũ (có logs/)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "public_test")
    ap.add_argument("--twin-threshold", type=float, help="mặc định theo configs/default.json; -1 tắt cổng")
    args = ap.parse_args(argv)
    threshold = load_config(DEFAULT_CONFIG).twin_threshold if args.twin_threshold is None else args.twin_threshold
    changes = replay(args.run, args.out, args.data, None if threshold is not None and threshold < 0 else threshold)
    print(f"{'thay đổi':16}{'lý do':62}{'hàm':24}{'câu':>5}")
    for (what, reason, fn), n in sorted(changes.items(), key=lambda x: (x[0][0] != "giữ nguyên", x[0])):
        print(f"{what:16}{reason:62}{fn:24}{n:5}")
    print(f"→ {args.out / 'submission.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
