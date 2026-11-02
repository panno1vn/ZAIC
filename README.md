# DataMate — Zalo AI Challenge 2026

Agent trả lời câu hỏi tiếng Việt trên dữ liệu kinh doanh của cửa hàng nhỏ (csv, xlsx, sqlite).
Kiến trúc: [docs/architecture/DataMate_kien_truc_v2.png](docs/architecture/DataMate_kien_truc_v2.png) · Kế hoạch: [docs/KE_HOACH_DataMate.md](docs/KE_HOACH_DataMate.md)

## Cài đặt (Windows, Python 3.10+)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt   # requirements.txt (chạy) + pytest (phát triển)
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
| Chạy agent trên một split | `python -m datamate.predict --data data/public_test --out outputs/run_public` |
| Chạy với mapping tay của cửa hàng train và chấm luôn (chỉ để phát triển) | `python -m datamate.eval.oracle --business biz_101 --out outputs/oracle_biz101` |
| Chạy toàn bộ test | `python -m pytest` (nhanh) · `python -m pytest -m slow` (chạy cả split public thật, ~1,5 phút; chạy trước mỗi lần nộp) |
| So hai rulebook / dựng lại luật tham chiếu | `python -m datamate.rules diff data/train/rulebook.md data/public_test/rulebook.md` · `python -m datamate.rules build data/train/rulebook.md data/public_test/rulebook.md` |
| Chấm một file nộp trên train | `python -m datamate.eval.run --pred outputs/submission.jsonl` |
| Kiểm tra scorer (đáp án tự chấm, phải được PA = 1) | `python -m datamate.eval.run --gold` |
| Lưu kết quả từng câu để phân tích lỗi | thêm `--save outputs/eval/ten_file.jsonl` |
| Kiểm tra định dạng trước khi nộp public | `python -m datamate.eval.validate --pred outputs/submission.jsonl --split public_test` |

Báo cáo của `datamate.eval.run` chia theo kiểu đáp án, theo ngành và theo cửa hàng; mỗi bảng xếp nhóm có PA thấp nhất lên đầu.

## Cấu trúc

```
datamate/
├── contracts/    # hợp đồng giữa các khối (Pydantic) + JSON schema   → docs/contracts.md
├── loader/       # [A] [A2] đọc + làm sạch, profiling               (G1)
├── mapping/      # [B] map về schema chuẩn, data card                (G2)
├── nlu/          # [C] hiểu câu hỏi, [C3] nối thực thể               (G3, G6)
├── temporal/     # [C2] tính ngày                                    (G4)
├── metrics/      # [D1] thư viện hàm + registry                      (G5)
├── codegen/      # [D2] sinh code dự phòng                           (G3)
├── rules/  verify/  decide/   # [R] [V] [E]                          (leader)
├── formatter/    # [F] format §9                                     (G4)
├── llm/          # client LLM dùng chung (có bản giả lập)
├── output/       # ghi submission từng dòng, log từng câu, đồng hồ chặn
├── pipeline.py   # nối mọi khối: từng cửa hàng, rồi từng câu
├── predict.py    # lệnh chạy chính
└── eval/         # scorer (§9), chạy đánh giá, kiểm tra file nộp — chỉ dùng khi phát triển
assets/plans/     # kế hoạch truy vấn mẫu (từ train)
assets/rules/     # văn bản luật tham chiếu cho [R]
tests/            # pytest
tools/research/   # script phân tích dữ liệu cho docs/research
docs/             # kiến trúc, kế hoạch, hợp đồng, nghiên cứu, data card, ghi chú luật
configs/  notebooks/  docker/
data/             # dữ liệu BTC (không commit)
outputs/          # file nộp, kết quả đánh giá (không commit)
```

Danh sách việc phải sửa để tăng điểm: [docs/HAN_CHE_VA_CAI_THIEN.md](docs/HAN_CHE_VA_CAI_THIEN.md).

Bộ khung chạy thật (05/11): với mapping tay, biz_101 được **28 đúng, 0 sai, 12 bỏ trống (PA +0,70)**. Khi chạy bình thường, mọi câu vẫn bỏ trống vì mapping tự động (G2) chưa có. Phiếu việc của từng gói nằm trong README của từng khối: [loader](datamate/loader/README.md) (G1), [mapping](datamate/mapping/README.md) (G2), [nlu](datamate/nlu/README.md) (G3, G6), [temporal](datamate/temporal/README.md) (G4), [metrics](datamate/metrics/README.md) (G5), [docker](docker/README.md) (G7). Quy trình làm việc: [CONTRIBUTING.md](CONTRIBUTING.md).
