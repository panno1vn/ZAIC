"""Retired 10/11 (leader decision). The team no longer keeps any answers to public test questions: the file this tool
used to read was another LLM's public answers, and contest Rule 6 forbids collecting answers to test questions by
any means. It was only ever used for aggregate counts and never reached the solution; it is now deleted.

Check public runs against our own earlier run instead (question by question, counts only):

    python tools/compare_runs.py <run_dir> outputs/public_live_778f898/submission.jsonl
"""
import sys

print("grade_public: retired (no public answer key is kept). Use tools/compare_runs.py <run_dir> <reference "
      "submission.jsonl> to compare with an earlier run.")
sys.exit(2)
