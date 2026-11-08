# DataMate: Zalo AI Challenge 2026

Hệ trả lời câu hỏi tiếng Việt về dữ liệu kinh doanh của cửa hàng nhỏ (csv, xlsx, sqlite). Đây là README nằm trong image Docker. Image chạy hoàn toàn không cần mạng: model, llama.cpp và mọi thư viện Python đều có sẵn trong image.

## Chạy

Lệnh chấm của BTC (Docker guideline 2026 §10), không tham số, không mạng, `/data` chỉ đọc:

```bash
docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g --entrypoint bash   -v /path/to/test:/data:ro -v /path/to/output:/result zaic2026_datamate_<team>:final /code/predict.sh
```

- **`/data`**: một split: `questions.jsonl`, `rulebook.md`, `calendar.csv`, `data/<business_id>/`. Đưa thư mục cha chứa đúng một split cũng được.
- **`/result/submission.jsonl`**: mỗi câu một dòng, ghi ngay khi có đáp án (dừng giữa chừng thì các câu đã ghi vẫn được chấm), đúng định dạng của đề.
- **`/result/logs/`** (guideline §3.3): mỗi câu một bản ghi trên một dòng, vừa ở file `<id>.json` vừa ở `questions.jsonl`, với:
  - `id`, `answer` (dòng đáp án cuối), `elapsed_ms` (từ lúc bắt đầu câu tới đáp án; câu đầu tiên của mỗi cửa hàng gồm cả thời gian đọc và map dữ liệu cửa hàng, ghi riêng ở `business_prep_ms`);
  - `thinking`: `null`, vì Qwen3 được gọi với chế độ suy nghĩ tắt (`enable_thinking: false`), không sinh suy luận; đầu ra có cấu trúc của mỗi lần gọi LLM (plan JSON) nằm ở `reading.llm_raw` (và `reading.llm_raw_retry` nếu gọi lại);
  - câu tính bằng hàm có sẵn: `code` (`datamate/metrics/<module>.py::<hàm>`), `inputs` (thư mục cửa hàng và plan đã giải: kỳ, chỉ số, bộ lọc, tên đã nối vào dữ liệu), `output` (giá trị hàm trả). Không sinh code tự do;
  - thêm: câu hỏi, plan, các cổng kiểm tra, quyết định.

  Mỗi cửa hàng có thêm `_business_<id>.json` (mapping dùng cho cửa hàng và kết quả kiểm tra); `llama_server.log` là log của server.
- `predict.sh` (thiết lập cố định, BTC không cần sửa): model `/code/models/model.gguf`, một GPU (card đầu tiên được cấp), giải mã tham lam, seed 0, một slot, tắt suy nghĩ. Nếu server không lên thì chạy riêng bộ đọc câu bằng luật nên vẫn ra file nộp. Ngân sách 5,5 giờ (`configs/default.json`) tính từ lúc bắt đầu, kể cả nạp model; hết giờ thì các câu còn lại ghi `abstain`. In ra `Model load time`, `Prediction time`, `Total time`.
- Thời gian đo được: public 1000 câu ≈ 41 phút trên laptop (≈ 2,5 giây/câu, nạp model < 1 phút); 500 câu private ước ≈ 21 phút.

## Bố cục trong image

| Đường dẫn | Nội dung |
|---|---|
| `/code/predict.sh` | điểm vào |
| `/code/README.md` | file này |
| `/code/requirements.txt` | thư viện Python (đã cài) |
| `/code/datamate/` | mã suy luận (đọc file, mapping, đọc câu, hàm tính, kiểm tra, định dạng) |
| `/code/assets/` | tài sản dựng từ train mà mã suy luận đọc (kho plan ví dụ, mapping mẫu, từ đồng nghĩa, luật tham chiếu) |
| `/code/configs/` | thiết lập chạy |
| `/code/models/model.gguf` | trọng số Qwen3-8B Q4_K_M |
| `/code/llama/` | `llama-server` (llama.cpp b12064, build cho sm_120) |
| `/code/tools/` | công cụ phát triển (đo, dựng tài sản) |
| `/code/training_code/` | dữ liệu train, đầu ra LLM đã dùng, mã dựng tài sản, log, `data_manifest.json` (xem README trong đó) |

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

| Model | Nguồn | Phát hành | Giấy phép | Tham số |
|---|---|---|---|---|
| Qwen3-8B, bản lượng tử GGUF Q4_K_M (`Qwen3-8B-Q4_K_M.gguf`) → `/code/models/model.gguf` | https://huggingface.co/Qwen/Qwen3-8B-GGUF, revision: `<ghi commit khi tải>`, SHA-256 file: `<ghi khi tải>` | 29/04/2025 (Qwen3) | Apache-2.0 | 8,2 tỉ (một model duy nhất, không MoE, không model phụ) |

Không tinh chỉnh; dùng nguyên bản phát hành. Tổng tham số mọi model suy luận: 8,2 tỉ ≤ 15 tỉ.

| Thành phần khác | Giấy phép |
|---|---|
| llama.cpp `llama-server` (tag b12064) | MIT |
| numpy, pandas | BSD-3-Clause |
| openpyxl, python-calamine, pydantic, rapidfuzz | MIT |
| rank-bm25 | Apache-2.0 |

## Dữ liệu

- Chỉ dùng dữ liệu train BTC phát hành (30 cửa hàng, 3000 câu có đáp án) và model công khai ở trên. Không dùng dữ liệu public / private test để dựng gì (chỉ đọc lời văn rulebook public làm bản luật tham chiếu, không đáp án nào).
- Không có tập validation tách riêng: các hàm và luật được kiểm trên chính train (`training_code/README.md`): mã cuối đúng 2752, sai 0, bỏ trống 248 trên 3000 câu.
- Chi tiết, lệnh dựng lại và checksum: `/code/training_code/README.md`, `/code/training_code/data_manifest.json`.

Không gọi dịch vụ ngoài nào. Container chạy được với `--network none`.
