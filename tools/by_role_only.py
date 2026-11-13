"""Train shops mapped as a shop of a format no example shares: only the last path of transfer.map_by_transfer (tables
paired by role, columns by meaning, both by the LLM), the paths by column names, by file names and by the README
switched off, the shop's own hand mapping left out of the examples. Scored against the train answers with the stored
plans, as eval.mapping does. This is the closest train comes to an unfamiliar private shop's mapping (N199).

    python tools/by_role_only.py                          # every train shop (~1 h with a live server, then cached)
    python tools/by_role_only.py biz_105 biz_117 biz_121  # some
    python tools/by_role_only.py --tries 2 biz_105        # the examples tried by role (default transfer.BY_ROLE_TRIES)

Needs llama-server on 8091 for the calls outside outputs/llm_cache_by_role_only.jsonl. Development only: train data.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import datamate.eval.mapping as em  # noqa: E402
from datamate.mapping import from_readme, transfer  # noqa: E402

CACHE = "outputs/llm_cache_by_role_only.jsonl"


def main(argv: list[str]) -> int:
    if "--tries" in argv:
        i = argv.index("--tries")
        tries = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
        full = transfer.map_by_transfer
        transfer.map_by_transfer = lambda raw, pool=None, llm=None, **kw: full(raw, pool, llm, by_role_tries=tries, **kw)
    transfer.candidates = lambda raw, pool=None: []
    transfer.sibling_files = lambda raw, pool=None: []
    readme = from_readme.map_from_readme

    def side_tables_only(raw):  # enrich still borrows the README's side tables; the README's own mapping is off
        if sys._getframe(1).f_code.co_name == "map_by_transfer":
            return None, "tắt: chỉ đo đường ghép theo vai trò"
        return readme(raw)
    from_readme.map_from_readme = side_tables_only
    shops = ["--business", *argv] if argv else []
    return em.main([*shops, "--llm-url", "http://127.0.0.1:8091", "--llm-cache", CACHE])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
