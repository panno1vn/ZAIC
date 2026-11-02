"""submission.jsonl written one line at a time and flushed, so a run stopped by the 6-hour limit keeps every answer
written so far (DataMate technical requirement 8)."""
from __future__ import annotations

import json
from pathlib import Path

from datamate.contracts import SubmissionLine


class SubmissionWriter:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.written: set[str] = set()
        self._fh = open(path, "w", encoding="utf-8", newline="\n")

    def write(self, line: SubmissionLine) -> bool:
        """Append one line; a question already written is skipped (first answer wins). True if written."""
        if line.id in self.written:
            return False
        text = json.dumps(line.to_dict(), ensure_ascii=False, allow_nan=False)  # NaN is not JSON: raise, never write it
        self._fh.write(text + "\n")
        self._fh.flush()
        self.written.add(line.id)
        return True

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "SubmissionWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
