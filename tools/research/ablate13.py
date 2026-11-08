"""Ablation set 13 (08/11) from run11_s41r (0.804): the two groups with the most wrong answers of S27 (count_where
6/58, phone shops 4/58) split by threshold entity and by shop. Counts only. See docs/CAN_XAC_MINH.md "Bộ nộp 13".

    python tools/research/ablate13.py <run_dir> <out_dir> <phone shop id> [<phone shop id> …]
"""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
run = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(exist_ok=True)
sub = [json.loads(l) for l in open(run / "submission.jsonl", encoding="utf-8") if l.strip()]
logs = {d["id"]: d for d in (json.loads(p.read_text(encoding="utf-8")) for p in (run / "logs").glob("q_*.json"))}

def cw(entity_set):
    return lambda d: (d.get("plan") or {}).get("intent") == "count_where" and \
        ((d.get("plan") or {}).get("threshold") or {}).get("entity") in entity_set
PHONE_SHOPS = tuple(sys.argv[3:])  # the shops to split out one by one, given on the command line
groups = {
    "bo_cw_khach": cw({"customer"}),                       # "khách có từ N đơn trở lên"
    "bo_cw_ngay_don": cw({"day", "order"}),                # "ngày / đơn có doanh thu từ X"
    "bo_cw_khac": cw({"product", "vehicle"}),              # mặt hàng, xe
}
groups.update({f"bo_shop_{b}": (lambda d, b=b: d["business_id"] == b) for b in PHONE_SHOPS})
for name, pick in groups.items():
    n = 0
    with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
        for a in sub:
            d = logs[a["id"]]
            if a["type"] not in ("abstain", "unanswerable") and pick(d):
                a, n = {"id": a["id"], "type": "abstain"}, n + 1
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"{name}: {n} câu bỏ trống")
