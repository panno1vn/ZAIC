"""Where a run's answers stop, from its own logs (no answers needed): answered / blank per business, blank questions
by pipeline stage, answers by function and by twin evidence. Use it on public runs, where nothing else is known.

    python tools/run_stats.py outputs/public_run1
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def stage(d: dict) -> str:
    s = d.get("signals") or {}
    if not s.get("mapping_ok", True):
        return "1 mapping hỏng"
    if d.get("plan") is None:
        return "2 không đọc được câu (plan)"
    if s.get("out_of_scope"):
        return "3 ngoài phạm vi"
    if d.get("result") is None:
        return "4 hàm không ra kết quả"
    return "5 cổng: " + d["decision"].get("reason", "")[:50]


def main(run: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    per, stages, functions, twins = defaultdict(Counter), Counter(), Counter(), Counter()
    for f in (Path(run) / "logs").glob("q_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        answered = d["decision"]["kind"] != "abstain"
        per[d["business_id"]]["answer" if answered else "blank"] += 1
        if not answered:
            stages[stage(d)] += 1
            continue
        functions[d["result"]["function"]] += 1
        t = d.get("twin") or {}
        score = 101 if t.get("baseline_agrees") else t.get("score", 0)
        twins["baseline đồng ý" if score == 101 else "≥ 90" if score >= 90 else "80–90" if score >= 80 else "< 80"] += 1
    print("cửa hàng   trả lời  bỏ trống")
    for b in sorted(per):
        print(f"  {b:9} {per[b]['answer']:6} {per[b]['blank']:8}")
    print("\nbỏ trống theo bước:")
    for s, n in sorted(stages.items()):
        print(f"  {n:4} {s}")
    print("\ntrả lời theo hàm:", dict(functions.most_common()))
    print("trả lời theo điểm giống câu anh em:", dict(twins))


if __name__ == "__main__":
    main(sys.argv[1])
