"""Write assets/mappings/signatures.json: the columns of every raw table the hand mappings of train read, so the
mapping transfer (datamate/mapping/transfer.py) can tell which table of a new shop plays the part of which table of a
mapped one without the train files (they are not in the Docker image).

    python tools/mapping_signatures.py

Development only: reads the train businesses that have a hand mapping.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datamate import loader  # noqa: E402
from datamate.eval.oracle import mapping_files  # noqa: E402
from datamate.mapping.transfer import SIGNATURES, column_notes, readme_columns  # noqa: E402


def samples(column, n: int = 3) -> list[str]:
    """A few distinct values of a raw column, for the column-matching prompt (transfer.py, by meaning)."""
    values = [str(v).strip() for v in column.dropna().unique()[:50] if str(v).strip()]
    return values[:n]


def main() -> int:
    out = {}
    for business in sorted(mapping_files("train")):
        raw = loader.load_business(ROOT / "data" / "train" / "data" / business)
        readme = readme_columns(raw.readme)
        out[business] = {t.table_id: {"columns": [str(c) for c in t.frame.columns],
                                      "samples": {str(c): samples(t.frame[c]) for c in t.frame.columns},
                                      "notes": column_notes(readme, t.table_id)}
                         for t in raw.tables}
    SIGNATURES.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} cửa hàng, {sum(len(v) for v in out.values())} bảng → {SIGNATURES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
