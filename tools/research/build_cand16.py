"""Bộ nộp 16: bản chính mới và một bản chẩn đoán, so với bản đã nộp có điểm.

    python tools/research/build_cand16.py <bản mới submission.jsonl> <bản đã nộp submission.jsonl> <thư mục ra>

Ra hai file:
- `chinh.jsonl`: bản mới, nguyên vẹn.
- `giu_cu_cau_doi.jsonl`: bản mới, nhưng các câu bản cũ đã trả lời mà bản mới đổi đáp án thì lấy lại đáp án cũ.

Đọc kết quả (điểm public tính trên 1000 câu, +1 đúng, −1 sai, 0 trống):
- nhóm "đổi đáp án": (điểm chính − điểm giu_cu) × 1000 / 2 = số câu chuyển sai → đúng trừ số câu chuyển đúng → sai;
- nhóm "câu mới" (bản cũ trống): điểm giu_cu − điểm bản cũ = (đúng − sai) của các câu mới (cộng phần câu bỏ, nếu có).
Chỉ in số đếm theo nhóm, không in câu hỏi hay đáp án.
"""
import json
import sys
from pathlib import Path


def read(path: Path) -> dict[str, dict]:
    return {json.loads(line)["id"]: json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()}


def answered(line: dict | None) -> bool:
    return line is not None and line.get("type") != "abstain"


def main() -> None:
    new, old, out = read(Path(sys.argv[1])), read(Path(sys.argv[2])), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    changed = [i for i in new if answered(old.get(i)) and answered(new[i]) and new[i] != old[i]]
    fresh = [i for i in new if not answered(old.get(i)) and answered(new[i])]
    dropped = [i for i in new if answered(old.get(i)) and not answered(new[i])]
    keep = {i: (old[i] if i in set(changed) else line) for i, line in new.items()}
    for name, lines in (("chinh.jsonl", new), ("giu_cu_cau_doi.jsonl", keep)):
        with open(out / name, "w", encoding="utf-8") as f:
            for line in lines.values():
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(f"câu đổi đáp án: {len(changed)}; câu mới: {len(fresh)}; câu bỏ: {len(dropped)}; "
          f"trả lời: {sum(answered(x) for x in new.values())} / {len(new)}")


if __name__ == "__main__":
    main()
