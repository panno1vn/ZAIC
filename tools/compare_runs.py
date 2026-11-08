"""Compare a new run's submission with a reference one, question by question: counts by shop, kind of change and the
function (from the new run's logs). Prints counts only, never a question or an answer.

    python tools/compare_runs.py outputs/docker_public outputs/public_run11/submission.jsonl
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
run, ref = Path(sys.argv[1]), Path(sys.argv[2])


def load(p):
    return {json.loads(l)["id"]: json.loads(l) for l in open(p, encoding="utf-8") if l.strip()}


def kind(a):
    t = a.get("type")
    return "trống" if t == "abstain" else "unans" if t == "unanswerable" else "trả lời"


new, old = load(run / "submission.jsonl"), load(ref)
shop = {json.loads(l)["id"]: json.loads(l)["business_id"]
        for l in open(ROOT / "data/public_test/questions.jsonl", encoding="utf-8-sig") if l.strip()}
by_shop, by_change = Counter(), Counter()
same = 0
for q in shop:
    a, b = old.get(q, {"type": "abstain"}), new.get(q, {"type": "abstain"})
    if a == b:
        same += 1
        continue
    log = run / "logs" / f"{q}.json"
    d = json.loads(log.read_text(encoding="utf-8")) if log.exists() else {}
    fn = (d.get("result") or {}).get("function", "-") if isinstance(d.get("result"), dict) else "-"
    change = f"{kind(a)} → {kind(b)}" if kind(a) != kind(b) else "đổi giá trị"
    by_shop[(shop[q], change)] += 1
    by_change[(change, fn)] += 1
print(f"giống: {same} / {len(shop)}; khác: {len(shop) - same}")
# an exception in the pipeline answers blank, so a blank kept blank hides it (08/11: 5 errors looked "the same")
errors = sum("error" in json.loads(f.read_text(encoding="utf-8")) for f in (run / "logs").glob("q_*.json")) \
    if (run / "logs").exists() else 0
print(f"LỖI khi chạy (log có 'error'): {errors}" + ("  ← xem lại trước khi nộp" if errors else ""))
print("trả lời:", sum(kind(x) == "trả lời" for x in new.values()), "(tham chiếu", sum(kind(x) == "trả lời" for x in old.values()), ")")
print("\ntheo cửa hàng:")
for k, n in sorted(by_shop.items()):
    print(f"  {n:4} {k[0]} {k[1]}")
print("\ntheo kiểu đổi và hàm (lượt mới):")
for k, n in sorted(by_change.items()):
    print(f"  {n:4} {k[0]:18} {k[1]}")
