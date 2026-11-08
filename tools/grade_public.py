"""Grade a public submission with Penalized Accuracy (PA = (right − wrong) / N; an answer to an unanswerable question
is wrong) against the public answer key the team received (data/grading/public_answers.jsonl, read-only).

    python tools/grade_public.py outputs/public_run12/submission.jsonl [more submissions…]

Grading only. The key is never read by datamate/ (tests/test_grading_isolation.py), never shipped (.dockerignore,
.gitignore) and this tool prints only counts, never a question or an answer: it stands in for the leaderboard, it is
not a source of rules (no training or hand-labelling on test data). The key has no "alias" field, so a name answer the
official key accepts by its code or another spelling counts wrong here: PA reads a little low (0.736 here for the
submission the leaderboard scored 0.744).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate.eval.scorer import score_line  # noqa: E402

KEY = ROOT / "data" / "grading" / "public_answers.jsonl"
QUESTIONS = ROOT / "data" / "public_test" / "questions.jsonl"


def _lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def grade(sub: Path) -> None:
    key = _lines(KEY)
    shop = {q["id"]: q["business_id"] for q in _lines(QUESTIONS)}
    pred = {p["id"]: p for p in _lines(sub)}
    total, by_type, by_shop = Counter(), defaultdict(Counter), defaultdict(Counter)
    for ref in key:
        outcome = score_line(pred.get(ref["id"]), ref).outcome
        total[outcome] += 1
        by_type[ref["type"]][outcome] += 1
        by_shop[shop.get(ref["id"], "?")][outcome] += 1
    n = len(key)
    pa = (total["correct"] - total["wrong"]) / n
    print(f"\n{sub}")
    print(f"  right {total['correct']} · wrong {total['wrong']} · abstain {total['abstain']} · PA {pa:+.3f}")

    def table(title: str, groups: dict) -> None:
        print(f"  {title:14}{'right':>7}{'wrong':>7}{'blank':>7}{'PA':>8}")
        for k, c in sorted(groups.items(), key=lambda kv: (kv[1]["correct"] - kv[1]["wrong"]) / sum(kv[1].values())):
            m = sum(c.values())
            print(f"  {k:14}{c['correct']:7}{c['wrong']:7}{c['abstain']:7}{(c['correct'] - c['wrong']) / m:+8.3f}")
    table("by key type", by_type)
    table("by shop", by_shop)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not KEY.exists():
        print(f"missing {KEY}", file=sys.stderr)
        return 1
    for a in argv or [str(ROOT / "outputs" / "public_run12" / "submission.jsonl")]:
        grade(Path(a))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
