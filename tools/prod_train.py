"""Train read as the run reads a shop it never saw: the real pipeline (pipeline.answer_question) with the live LLM, the
shop's data card, the verified bank minus every example of the same shop, the twin gate; scored against the answers.
Mapping by transfer with the cached column matching (as eval_cached). Every `step`-th question. Counts, the N79 retries
(first plan refused by the grounding gates) apart, and the wrong ones.

    python tools/prod_train.py <step> <out.jsonl> [--ground-retry]     # needs llama-server on 8091; step 2 ≈ 1 h
"""
import json
import sys
import urllib.error
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import datamate.nlu as nlu  # noqa: E402
from datamate import pipeline, rules  # noqa: E402
from datamate.eval.scorer import score_line  # noqa: E402
from datamate.llm import CachedLLM, LlamaServerLLM  # noqa: E402
from datamate.mapping import transfer  # noqa: E402
from datamate.nlu import prompt  # noqa: E402
from datamate.predict import DEFAULT_CONFIG, load_config  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
step, out_path = int(sys.argv[1]), Path(sys.argv[2])
nlu.GROUND_RETRY = "--ground-retry" in sys.argv  # N79 is off by default


class _Offline:
    def generate_json(self, messages, schema):
        raise urllib.error.URLError("offline")

    def healthy(self):
        return True


split = ROOT / "data/train"
qs = [json.loads(l) for l in open(split / "questions.jsonl", encoding="utf-8-sig") if l.strip()][::step]
refs = {json.loads(l)["id"]: json.loads(l) for l in open(split / "answers.jsonl", encoding="utf-8")}
rulebook = (split / "rulebook.md").read_text(encoding="utf-8-sig")
status = rules.check_rules(rulebook, pipeline.rule_ids())
mapper = CachedLLM(_Offline(), str(ROOT / "outputs/llm_cache_mapping.jsonl"))
live = CachedLLM(LlamaServerLLM("http://127.0.0.1:8091", timeout_s=120), str(ROOT / "outputs/llm_cache_prod_train.jsonl"))
twin = load_config(DEFAULT_CONFIG).twin_threshold
same = {}
for e in prompt.default_bank().items:
    same.setdefault(e.get("business_id"), set()).add(e["id"])
ctxs, c, wrong = {}, Counter(), []
with open(out_path, "w", encoding="utf-8", buffering=1) as fh:
    for n, q in enumerate(qs, 1):
        b = q["business_id"]
        if b not in ctxs:
            pool = transfer.examples(leave_out=b)
            ctxs[b] = pipeline.prepare_business(
                split / "data" / b, rulebook, None,
                lambda raw, p, rb, _l=None, pool=pool: transfer.map_by_transfer(raw, pool, llm=mapper)[0] or transfer.failed([]))
        excl = frozenset(same.get(b, set()))
        line, rec = pipeline.answer_question(q, ctxs[b], split / "calendar.csv", status, rulebook, live, twin, excl)
        o = score_line(line.to_dict(), refs[q["id"]]).outcome
        rd = rec.get("reading") or {}
        kind = "N79" if "rejected_first" in rd else ("N78" if rd.get("retry") else "first")
        c[(kind, rd.get("retry", "-"), o)] += 1
        if o == "wrong":
            wrong.append((kind, b, q["question"][:100], json.dumps(line.to_dict(), ensure_ascii=False)[:110],
                          json.dumps(refs[q["id"]].get("answer"), ensure_ascii=False)[:80]))
        fh.write(json.dumps({"id": q["id"], "kind": kind, "retry": rd.get("retry"), "outcome": o}, ensure_ascii=False) + "\n")
        if n % 200 == 0:
            print(f"  {n}/{len(qs)}", dict(Counter(k[2] for k in c.elements())), flush=True)
tot = Counter()
for (k, r, o), v in c.items():
    tot[o] += v
print(len(qs), "questions:", dict(tot))
for k, v in sorted(c.items()):
    print(" ", v, k)
for w in wrong:
    print("WRONG", w)
