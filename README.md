# DataMate — Zalo AI Challenge 2026

Agent trả lời câu hỏi tiếng Việt trên dữ liệu kinh doanh của cửa hàng nhỏ (csv, xlsx, sqlite).
Kiến trúc: [docs/architecture/DataMate_kien_truc_v2.png](docs/architecture/DataMate_kien_truc_v2.png) · Kế hoạch: [docs/KE_HOACH_DataMate.md](docs/KE_HOACH_DataMate.md)

## Cài đặt (Windows, Python 3.10+)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Giải nén dữ liệu của BTC vào `data/` (thư mục này không được commit):

```
data/
├── train/         # questions.jsonl, answers.jsonl, rulebook.md, calendar.csv, data/<biz>/
└── public_test/   # questions.jsonl, rulebook.md, calendar.csv, data/<biz>/
```

## Lệnh thường dùng

| Việc | Lệnh |
|---|---|
| Chạy toàn bộ test | `python -m pytest` |
| Chấm một file nộp trên train | `python -m datamate.eval.run --pred outputs/submission.jsonl` |
| Kiểm tra scorer (đáp án tự chấm, phải được PA = 1) | `python -m datamate.eval.run --gold` |
| Lưu kết quả từng câu để phân tích lỗi | thêm `--save outputs/eval/ten_file.jsonl` |
| Kiểm tra định dạng trước khi nộp public | `python -m datamate.eval.validate --pred outputs/submission.jsonl --split public_test` |

Báo cáo của `datamate.eval.run` chia theo kiểu đáp án, theo ngành và theo cửa hàng; mỗi bảng xếp nhóm có PA thấp nhất lên đầu.

## Cấu trúc

```
datamate/         # code của agent
└── eval/         # scorer (§9), chạy đánh giá, kiểm tra file nộp — chỉ dùng khi phát triển
tests/            # pytest
docs/             # kiến trúc, kế hoạch, data card, ghi chú luật
configs/  assets/  notebooks/  docker/
data/             # dữ liệu BTC (không commit)
outputs/          # file nộp, kết quả đánh giá (không commit)
```

Các khối còn lại ([A]…[F]) được thêm từ T3 03/11 theo kế hoạch. Quy trình làm việc: [CONTRIBUTING.md](CONTRIBUTING.md).
