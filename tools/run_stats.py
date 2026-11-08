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


def no_result_reason(d: dict) -> str:
    """Why a plan gave no result, from the log's no_result (N72): the step, and the function or the missing key."""
    nr = d.get("no_result") or {}
    w = nr.get("why")
    if w is None:
        return "(log cũ, không ghi lý do)"
    if w == "no_function":
        return f"chưa có hàm {tuple(nr.get('key') or ())}"
    if w == "filter_not_taken":
        return f"bộ lọc hàm không nhận: {nr.get('function')} {nr.get('fields')}"
    if w == "function_none":
        return f"hàm trả None: {nr.get('function')}"
    return w


def main(run: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    per, stages, functions, twins = defaultdict(Counter), Counter(), Counter(), Counter()
    why, where = Counter(), Counter()  # stage 4 split by the log's no_result (N72); `at` only in a replay
    for f in (Path(run) / "logs").glob("q_*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        answered = d["decision"]["kind"] != "abstain"
        per[d["business_id"]]["answer" if answered else "blank"] += 1
        if not answered:
            stages[stage(d)] += 1
            if stage(d).startswith("4"):
                why[no_result_reason(d)] += 1
                at = (d.get("no_result") or {}).get("at") or []
                if at:
                    where[at[0]] += 1
            continue
        functions[(d.get("result") or {}).get("function") or d["decision"]["kind"]] += 1  # unanswerable: no result
        t = d.get("twin") or {}
        score = 101 if t.get("baseline_agrees") else t.get("score", 0)
        twins["baseline đồng ý" if score == 101 else "≥ 90" if score >= 90 else "80–90" if score >= 80 else "< 80"] += 1
    print("cửa hàng   trả lời  bỏ trống")
    for b in sorted(per):
        print(f"  {b:9} {per[b]['answer']:6} {per[b]['blank']:8}")
    print("\nbỏ trống theo bước:")
    for s, n in sorted(stages.items()):
        print(f"  {n:4} {s}")
    if why:
        print("\nbước 4 theo lý do (N72):")
        for w, n in why.most_common():
            print(f"  {n:4} {w}")
    if where:
        print("\nbước 4, dòng dừng (chỉ có ở lượt đọc lại):")
        for w, n in where.most_common(25):
            print(f"  {n:4} {w}")
    print("\ntrả lời theo hàm:", dict(functions.most_common()))
    print("trả lời theo điểm giống câu anh em:", dict(twins))


if __name__ == "__main__":
    main(sys.argv[1])
