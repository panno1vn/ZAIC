import json, re, sys, unicodedata, difflib
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding="utf-8")
per = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
qs = {q["id"]: q for q in map(json.loads, open("data/train/questions.jsonl", encoding="utf-8"))}
ans = {a["id"]: a for a in map(json.loads, open("data/train/answers.jsonl", encoding="utf-8"))}
out = {r["id"]: r for r in per}
def norm(s):
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", re.sub(r"[^\w\s/%]", " ", s))).strip()
N = {i: norm(q["question"]) for i, q in qs.items()}
blank = [r for r in per if r["outcome"] == "abstain"]
print("blank", len(blank), "| by stage-kind:", Counter(r["stage"].split(":")[0] for r in blank))
print("by answer type:", Counter(ans[r["id"]]["type"] for r in blank))
print("by shop:", sorted(Counter(r["business_id"] for r in blank).items(), key=lambda x: -x[1]))
rows = []
for r in blank:
    me = N[r["id"]]; b = r["business_id"]
    tw = [j for j in qs if qs[j]["business_id"] != b and difflib.SequenceMatcher(None, me, N[j]).ratio() >= 0.85]
    oc = Counter(out[j]["outcome"] for j in tw)
    rows.append((r, len(tw), oc))
cls = Counter()
for r, n, oc in rows:
    k = "khong co sinh doi" if n == 0 else ("sinh doi cung trong" if oc["correct"] == 0 else "sinh doi tra loi dung")
    cls[k] += 1
print("twin classes:", cls)
print()
for r, n, oc in sorted(rows, key=lambda x: (x[0]["stage"].split(":")[0], -(x[1] - x[2]["correct"]))):
    a = ans[r["id"]]
    print(f'{r["business_id"]} | {r["stage"][:60]:60} | {a["type"]:12} | twins {n:2} (dung {oc["correct"]}, trong {oc["abstain"]}) | {qs[r["id"]]["question"][:95]}')
