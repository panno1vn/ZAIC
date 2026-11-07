# DataMate: Zalo AI Challenge 2026

Hệ trả lời câu hỏi tiếng Việt về dữ liệu kinh doanh của cửa hàng nhỏ (csv, xlsx, sqlite). Đây là README nằm trong image Docker. Image chạy hoàn toàn không cần mạng: model, llama.cpp và mọi thư viện Python đều có sẵn trong image.

## Chạy

```bash
docker run --rm --gpus all --network none \
  -v /đường/dẫn/test:/data:ro -v /đường/dẫn/kết_quả:/result zaic-datamate:v1
```

- **`/data`**: thư mục của một split, gồm `questions.jsonl`, `rulebook.md`, `calendar.csv`, `data/<business_id>/`. Nếu đưa vào thư mục cha chứa đúng một split thì hệ cũng tự tìm thấy.
- **`/result/submission.jsonl`**: mỗi câu hỏi một dòng, đúng định dạng của đề (`number`, `percent`, `string`, `date`, `boolean`, `list`, `table`, `unanswerable`, `abstain`).
- **`/result/logs/`**: mỗi câu hỏi một file `<id>.json`, gồm:
  - câu hỏi;
  - plan đọc được từ câu hỏi;
  - kỳ đã quy ra ngày;
  - hàm và số liệu dùng để tính;
  - các cổng kiểm tra;
  - quyết định và đáp án cuối;
  - thời gian chạy (`elapsed_ms`).

  Mỗi cửa hàng có thêm một file `_business_<id>.json`, ghi mapping dùng cho cửa hàng đó và kết quả các bước kiểm tra. Ngoài ra có `llama_server.log`.
- `predict.sh` mở `llama-server` trên GPU đầu tiên, trả lời mọi câu hỏi, rồi tắt server. Nếu server không lên, hệ chạy riêng bộ đọc câu bằng luật nên vẫn ra file nộp, chỉ ít câu trả lời hơn. Ngân sách thời gian là 5,5 giờ (`configs/default.json`), tính từ lúc tiến trình bắt đầu, kể cả thời gian nạp model. Hết giờ thì các câu còn lại được ghi `abstain`.

## Phương pháp

LLM không tự tính ra đáp án. LLM chỉ làm hai việc: **đọc câu hỏi thành một plan có cấu trúc** (JSON theo schema), và **ghép cột dữ liệu theo nghĩa** khi cửa hàng có định dạng lạ. Mọi con số do các hàm viết tay tính ra, mỗi hàm theo đúng một dòng của rulebook. Trả lời sai bị trừ điểm, nên chỉ cần một bước kiểm tra không qua là câu đó bỏ trống (`abstain`).

1. **[A] Đọc file** (`datamate/loader`): csv (nhận diện bảng mã), xlsx (mọi sheet, dòng tiêu đề nhiều tầng, dòng tổng), sqlite (mọi bảng). Mọi ô đọc dạng chữ; tiền, số, ngày được phân tích riêng theo cách viết Việt Nam.
2. **[M] Mapping về bảng chuẩn** (`datamate/mapping`): đơn, dòng hàng, danh mục, khách, phiếu thu, trả hàng, nhập hàng, tồn kho… Có bốn đường, thử lần lượt:
   1. chuyển mapping của một cửa hàng train cùng định dạng, khớp theo tên cột;
   2. cùng tên file, ghép cột theo nghĩa bằng LLM;
   3. dựng từ mô tả cột trong README của cửa hàng;
   4. định dạng chưa gặp: LLM ghép bảng theo vai trò (bảng đơn, dòng hàng…), rồi ghép cột theo nghĩa.

   Mapping nào cũng phải qua 11 bước kiểm tra trước khi được dùng, gồm cả kiểm tra nghĩa: thành tiền = số lượng × đơn giá, trạng thái đơn hợp lý, ngày cuối khớp README, dòng hàng thuộc đơn có thật. Không mapping nào qua thì mọi câu của cửa hàng đó bỏ trống.
3. **[N] Đọc câu hỏi** (`datamate/nlu`):
   - Qwen3-8B, giải mã tham lam (temperature 0, seed cố định), đầu ra bị ép theo JSON schema bằng grammar của llama.cpp. Prompt có thẻ dữ liệu của cửa hàng và các ví dụ train gần nhất (BM25).
   - Plan phải bám vào câu hỏi: ngày, năm, bộ lọc, tên hàng, tên khách đều phải có trong câu.
   - Một bộ đọc bằng luật chạy song song, dùng để đối chiếu.
4. **[T] Thời gian** (`datamate/temporal`): "tháng này", "tuần trước", "Tết" quy ra khoảng ngày theo `as_of_date` và `calendar.csv` (âm lịch).
5. **Nối tên** (`datamate/nlu/linking`): tên hàng hoặc tên khách viết tắt, không dấu, sai chính tả được khớp với tên có trong dữ liệu. Có nhiều ứng viên ngang nhau thì bỏ trống.
6. **[F] Hàm tính** (`datamate/metrics`): doanh thu, số đơn, số lượng, xếp hạng, so sánh, tỉ trọng, chuỗi theo kỳ, công nợ, tồn kho, nhập hàng, lãi gộp… Mỗi hàm ghi dòng rulebook nó dựa vào.
7. **[R] Rulebook** (`datamate/rules`): mỗi lần chạy, rulebook của split được so với bản tham chiếu. Hàm nào dựa vào một dòng luật đã đổi thì câu dùng hàm đó bỏ trống. Câu dùng thuật ngữ mới mà không hàm nào hiểu cũng bỏ trống.
8. **[V] Kiểm tra và [E] quyết định** (`datamate/verify`, `datamate/decide`):
   - kiểm tra kỳ có đủ dữ liệu không, số liệu có hợp lý không, bảng xếp hạng có bị hoà không;
   - kỳ nằm hoàn toàn ngoài khoảng ngày có dữ liệu thì trả lời `unanswerable` (§7);
   - các trường hợp khác không chắc chắn thì `abstain`.
9. **Định dạng** (`datamate/formatter`): làm tròn và kiểu đáp án theo bảng định dạng của rulebook.

## "Huấn luyện"

Không tinh chỉnh model nào. Phần dựng từ dữ liệu train nằm trong `assets/`. Mã dựng lại đi kèm image, trong `datamate/eval` và `tools/`.

| Tài sản | Là gì | Dựng lại |
|---|---|---|
| `assets/mappings/train/*.json` | mapping tay của 10 cửa hàng train (mẫu cho đường 1, 2, 4) | viết tay theo README từng cửa hàng; chữ ký cột: `python tools/mapping_signatures.py` |
| `assets/plans/verified_train.jsonl` | các plan đã kiểm chứng trên train (ví dụ cho prompt) | `python -m datamate.eval.build_bank` (cần llama-server) |
| `assets/plans/templates_train.json` | mẫu câu train | `python -m datamate.eval.build_bank` |
| `assets/linking/synonyms.json` | từ đồng nghĩa, viết tắt để nối tên | viết tay từ câu hỏi train |
| `assets/rules/reference_rules.json` | rulebook tham chiếu | `python -m datamate.rules build data/train/rulebook.md data/public_test/rulebook.md` |

Code không có logic theo id cửa hàng hay id câu hỏi. Điều này có test kiểm tra: `tests/test_no_id_logic.py`.

## Model và giấy phép

| Thành phần | Giấy phép |
|---|---|
| Qwen3-8B (GGUF Q4_K_M), `/models/model.gguf` | Apache-2.0 |
| llama.cpp `llama-server` (tag b12064, build cho sm_120) | MIT |
| numpy, pandas | BSD-3-Clause |
| openpyxl | MIT |
| python-calamine | MIT |
| pydantic | MIT |
| rapidfuzz | MIT |
| rank-bm25 | Apache-2.0 |

Không gọi dịch vụ ngoài nào. Container chạy được với `--network none`.
