"""eval.mapping on train without llama-server: the column matching reads the LLM cache (outputs/llm_cache_mapping.jsonl)
and the plans are the stored ones (outputs/bank/llm_plans.jsonl, or the file given). Prints the cache misses at the
end: 0 means the run is the one a live server would give (it decodes greedily with a fixed seed).

    python tools/eval_cached.py                                   # 8B plans, every train shop (~15 min)
    python tools/eval_cached.py --plans outputs/bank/llm_plans.14b_kaggle.jsonl
    python tools/eval_cached.py --business biz_106 biz_129

Development only: train data.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import datamate.eval.mapping as em  # noqa: E402
from datamate.llm import CachedLLM  # noqa: E402

MISSES = [0]


class _Offline:
    def generate_json(self, messages, schema):
        MISSES[0] += 1
        raise urllib.error.URLError("offline: cache miss")

    def healthy(self):
        return True


def main(argv: list[str]) -> int:
    if "--plans" in argv:
        i = argv.index("--plans")
        em.PLANS = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    em.connect_llm = lambda url, cache=None, **kw: CachedLLM(_Offline(), cache)
    code = em.main(argv + ["--llm-url", "offline"])
    print(f"PLANS: {em.PLANS}  CACHE MISSES: {MISSES[0]}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
