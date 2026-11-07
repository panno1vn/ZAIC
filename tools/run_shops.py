"""The public pipeline on some shops only, with the LLM (llama-server on 8091): to see how the LLM reads a shop's
questions after its hints or functions changed, without the full 40-minute run.

    python tools/run_shops.py outputs/public_phones dev_011 dev_014

Writes submission.jsonl (the other shops' questions absent) and logs/, which tools/replay_run.py can replay.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from datamate.pipeline import run  # noqa: E402
from datamate.predict import DEFAULT_CONFIG, connect_llm, load_config  # noqa: E402


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    out, shops = Path(argv[0]), set(argv[1:])
    config = load_config(DEFAULT_CONFIG)
    config.question_filter = lambda q: q["business_id"] in shops
    llm = connect_llm("http://127.0.0.1:8091")
    if llm is None:
        return 1
    summary = run(ROOT / "data" / "public_test", out, config, llm)
    print(summary.n_questions, dict(summary.types), "errors", summary.errors, f"{summary.elapsed_s:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
