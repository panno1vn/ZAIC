# Bàn giao phiên 3 → phiên 4

> **Đã có [BAN_GIAO_PHIEN_4.md](BAN_GIAO_PHIEN_4.md): phiên mới đọc file đó trước.** File này vẫn giữ lệnh mở llama-server, luật N22 và câu hỏi gửi BTC.

*Viết lại tối 04/11/2026 (ngày hệ thống), sau lần nộp public đầu tiên. Đóng băng 16/11 23:59.*

## Bắt đầu phiên mới thế nào
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_3.md`, rồi `docs/TIEN_DO.md` và mục 9–10 của `docs/KE_HOACH_DataMate.md`. Kiểm `git status` và test. Sau đó làm việc tiếp theo ở mục "Việc tiếp theo" của file bàn giao.

- **Python:** dùng `.venv\Scripts\python.exe`, không dùng `python` trần (Python 3.10 của hệ thống không có pytest). Test chạy bằng `.venv\Scripts\python.exe -m pytest -q`. Repo tắt dòng tổng kết của pytest; muốn đếm số test qua thì đếm dấu chấm.
- **LLM:** trưởng nhóm tự mở llama-server (Claude không tự chạy file .exe), cổng 8091. Giữ cửa sổ mở trong lúc chạy.
  ```powershell
  cd E:\llm\llama-b12064
  .\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
  ```
  Kiểm tra server sống: `curl http://127.0.0.1:8091/health`. Chạy cả public (1000 câu) mất khoảng 23 phút.

## Tình hình trong một đoạn
- Pipeline: loader → mapping tự động → Qwen3-8B đọc câu thành plan → hàm số liệu viết theo rulebook → cổng kiểm tra → trả lời hoặc bỏ trống.
- Trên train, mapping của chính cửa hàng luôn bị bỏ ra khi đo: **2294 đúng / 0 sai / 706 bỏ trống, PA +0,765**.
- **Public lượt 1: 0,316**, tức 343 đúng / **27 sai** trong 370 câu trả lời, 630 bỏ trống. Train báo 0 sai nhưng tỉ lệ sai thật trên cửa hàng mới là **7,3%**.
- Public mới map được 8/14 cửa hàng. Riêng 6 cửa hàng còn lại đã chiếm 360 câu bỏ trống.

## Kết quả public và chẩn đoán (04/11)
Hôm nay đã dùng hết 5 lượt nộp: 1 lượt thật, 4 lượt chẩn đoán. Mỗi lượt chẩn đoán bỏ trống thêm một nhóm câu của lượt 1. **Số sai của nhóm = (số câu − (0,316 − điểm) × 1000) / 2.**

| Lượt | Bỏ trống thêm | Câu | Điểm | Đúng | Sai |
|---|---|---:|---:|---:|---:|
| 1 (thật) | — | 370 trả lời | **0,316** | 343 | 27 |
| A | `sales.value_of` (một con số) | 190 | 0,148 | 179 | 11 (5,8%) |
| B | `sales.rank` + `sales.count_where` | 101 | 0,241 | 88 | **13 (12,9%)** |
| C | so sánh, tỉ trọng, chuỗi, xu hướng | 64 | 0,258 | 61 | 3 |
| D (suy ra) | công nợ, nhập hàng, đợt giao | 15 | — | 15 | 0 |
| < 80 | câu có điểm giống câu anh em < 80 | 65 | 0,257 | 62 | 3 |

**Đã loại:**
- **Thuật ngữ mới của rulebook public** ("khách trung thành nhất"…): các câu có thuật ngữ này đều đã bỏ trống. Vẫn thêm cổng R46 để phòng cho private.
- **Mapping:** 3 cửa hàng map được bằng hai đường độc lập (chuyển mẫu và dựng từ README) cho 140/140 câu giống nhau.
- **Câu diễn đạt lạ:** nhóm < 80 vẫn đúng 95%. **24/27 câu sai là câu trông quen.**

**Nghi ngờ còn lại**, chưa kiểm chứng:
- dữ liệu cửa hàng public bị hiểu sai giống nhau ở mọi đường mapping (chữ trạng thái đọc theo từ khoá, `unify_keys` gộp tên, quy đổi đơn vị, khách lẻ);
- cách tính hoặc trình bày của hàm xếp hạng / đếm: hoà hạng §9, tên in ra khác cách viết trong đáp án, ngưỡng "≥ N đơn".

**Nhận xét quan trọng:** hệ thống đang đúng 93%. Một cổng chặn chỉ lên điểm khi **hơn nửa số câu nó chặn là câu sai**. Chặn đại trà theo ngưỡng (ví dụ điểm giống < 80) chắc chắn làm tụt điểm.

**Bỏ trống ở lượt 1, theo bước** (`python tools/run_stats.py outputs/public_run1`):

| Bước | Câu |
|---|---:|
| Mapping hỏng (6 cửa hàng) | 360 |
| Hàm không ra kết quả | 128 |
| Không đọc được câu (plan) | 109 |
| Cổng câu anh em | 28 |
| Ngoài phạm vi | 5 |

Cửa hàng public theo cách map:
- theo tên cột: dev_001 (mẫu biz_115), dev_002 và dev_005 (biz_103), dev_006 (biz_123);
- theo nghĩa: dev_004 (biz_117), dev_007 và dev_008 (biz_101), dev_010 (biz_111);
- không map được: dev_003, 009, 011, 012, 013, 014.

## Việc tiếp theo
1. **05/11, 3 lượt chẩn đoán đã có file sẵn** trong `outputs/public_ablation/`, đều qua `eval.validate`, đều dựng từ lượt 1:

   | File | Đổi gì | Đọc kết quả |
   |---|---|---|
   | `tat_cong_cau_anh_em.jsonl` | trả lời thêm 28 câu chỉ bị cổng câu anh em chặn | điểm − 0,316 = (đúng − sai)/1000 của 28 câu; dương thì tắt cổng (N16) |
   | `bo_xep_hang.jsonl` | bỏ trống 54 câu `sales.rank` | số sai theo công thức; phần còn lại của 13 câu là `count_where` (47 câu) |
   | `bo_map_theo_nghia.jsonl` | bỏ trống 169 câu của 4 cửa hàng map theo nghĩa | số sai của đường map theo nghĩa; 201 câu còn lại là đường theo tên cột |

   Ghi điểm vào HAN_CHE N24 và TIEN_DO.
2. **Tìm nguyên nhân trên train và sửa**, theo nhóm vừa khoanh được. Không được xem dữ liệu public (xem N22).
   - Lỗi ở hàm xếp hạng / đếm: rà lại luật hoà hạng §9, tên trả về (`_first_name`, `unify_keys`), khách lẻ, dòng phí, ngưỡng.
   - Lỗi ở đường map theo nghĩa: rà các chốt R37/R43 và `read_word` (từ khoá trạng thái: "ok", "xong", "đang xử lý"…).

   Mỗi bản sửa phải có test, đo lại `eval.mapping` (0 sai), rồi chạy `predict` public và nộp.
3. **Câu "không trả lời được"** (rulebook dòng 98–100): train có 70/3000. `decide` đang tắt (`out_of_scope` → bỏ trống). Đo trên train trước rồi mới bật.
4. **Độ phủ, chỉ dùng train:** cho hệ đọc được định dạng của biz_110 (chỉ có đơn, không có dòng hàng), biz_123 (sqlite POS, README không mô tả cột) và biz_124 (3 nguồn). Ghi chú cũ, viết trước khi có quyết định N22, cho thấy dev_009 giống biz_110 và dev_003 gần biz_124: khoảng 150 câu.
5. **Câu hỏi gửi BTC (N22)**, trưởng nhóm gửi, chưa có trả lời:
   > Đội em muốn hỏi về mục 4.2 của thể lệ. Đội không gán nhãn, không xem đáp án, không viết xử lý riêng cho từng cửa hàng hay từng câu hỏi. Đội có được **xem cấu trúc file và README (đầu vào) của public test** để viết các luật đọc dữ liệu dùng chung cho mọi cửa hàng không, ví dụ thêm một cách gọi tên cột vào từ điển chung? Hay đội chỉ được phát triển dựa trên dữ liệu train? Đội cảm ơn BTC.
6. **Docker** (kế hoạch 10–12/11, nộp lần 1 ngày 14/11). Chưa bắt đầu, còn chờ guideline BTC. Cần:
   - llama-server CUDA ≥ 12.8 trong image;
   - chép `assets/` (H14);
   - chạy thử đủ 6 giờ trên máy GPU thuê. Laptop dùng 4G, không tải hay đẩy file lớn.
7. v2 còn lại (ít câu): tuổi nợ, giá trị tồn, lô / hạn dùng, tăng giá theo trung bình mỗi ngày.

## Luật và quyết định cần nhớ
- **N22 (trưởng nhóm quyết 04/11):** chỉ phát triển bằng dữ liệu train cho tới khi BTC trả lời. Không xem file, README hay câu hỏi của public để sửa code. Chỉ đếm số liệu tổng từ log của chính hệ thống, và nộp chẩn đoán theo **thành phần** (nhóm hàm, cách map, cổng), không theo từng câu.
- Không logic theo id cửa hàng hay câu hỏi trong code chạy thật, kể cả trong comment (`test_no_id_logic`). Mapping tay chỉ cho cửa hàng train.
- Mô hình ≤ 15B tham số, giấy phép OSI. Khi nộp, chọn loại mô hình kiểu "SLM / mã nguồn mở", **không** chọn "3rd APIs".
- Trưởng nhóm tự commit và push; Claude chỉ đưa lệnh. Hỏi trước khi tải file > 50 MB (mạng 4G). Trả lời bằng tiếng Việt và nêu căn cứ. Bug phải chạy thử xác nhận trước khi sửa; bản sửa nào cũng cần test và một mục trong HAN_CHE.

## Phiên 3 đã làm gì (tóm tắt; chi tiết ở HAN_CHE mục F–L)
| Việc | Kết quả | Ở đâu |
|---|---|---|
| T1 gom cụm mẫu câu | 450 cụm; 26 plan tay cho cụm LLM đọc sai | `nlu/templates.py`, `assets/plans/t1_reps.jsonl`, [research/templates.md](research/templates.md) |
| T2 nối tên | tên hàng nối 100% trên 220 câu có bộ lọc | `nlu/linking.py`, `assets/linking/` |
| T3 hàm bán hàng + nối LLM | `--llm-url`, `--llm-cache` | `metrics/sales.py`, `metrics/frames.py` |
| T4 kho đã kiểm chứng + cổng câu anh em | 2390 plan; cổng ngưỡng 0 (N16 còn mở) | `assets/plans/verified_train.jsonl`, `nlu/twins.py` |
| Cổng căn cứ (`nlu.accept_plan`) | bộ lọc, ngày, năm, chỉ số phải có căn cứ trong câu | `nlu/grounding.py` |
| v2 | nhập, giá, tồn, công nợ, lãi, đợt giao | `metrics/stock.py`, `debt.py`, `industry.py` |
| T5 mapping chuyển từ mẫu | theo tên cột; theo nghĩa (LLM chọn cột, có mô tả README); chốt R37/R43 | `mapping/transfer.py`, mapping tay biz_111, biz_115 |
| Review cuối phiên | R44 (mô tả README lấy nhầm bảng), R45 (ngày ảnh tồn chỉ khi README ghi rõ) | HAN_CHE mục L |
| N23 mapping dựng từ README | không cần LLM; cụm nghĩa → cột chuẩn; train 2048/0 khi đứng riêng | `mapping/from_readme.py` |
| R46 cổng thuật ngữ | thuật ngữ rulebook không có bản train mà hàm không dẫn thì bỏ trống | `rules.unverified_terms`, tín hiệu `terms_known` |
| Nộp public | lượt 1 0,316; 4 lượt chẩn đoán | `outputs/public_run1/`, `outputs/public_ablation/` |

Số đo train qua các bước (`eval.mapping`, plan LLM đã lưu):

| Thời điểm | Đúng | Sai | PA |
|---|---:|---:|---:|
| Sau T5 | 1881 | 0 | +0,627 |
| Sau N23 | 2277 | 0 | +0,759 |
| Thêm nhập hàng, đợt giao, giờ đặt đơn vào đường README | **2294** | **0** | **+0,765** |

Cả chuỗi với LLM thật (`oracle --all --auto-mapping`, v5, trước N23): 1815 / 0, PA +0,605.

## Lệnh hay dùng
| Việc | Lệnh (thay `python` bằng `.venv\Scripts\python.exe`) |
|---|---|
| Chạy public | `python -m datamate.predict --data data/public_test --out outputs/public_runN --llm-url http://127.0.0.1:8091` |
| Kiểm định dạng trước khi nộp | `python -m datamate.eval.validate --pred outputs/public_runN/submission.jsonl` |
| Đếm lý do bỏ trống của một lượt | `python tools/run_stats.py outputs/public_runN` |
| Chấm mapping tự động trên train | `python -m datamate.eval.mapping [--llm-url …] [--business …] [--readme-only]` |
| Cả chuỗi với mapping tự động | `python -m datamate.eval.oracle --all --auto-mapping --llm-url … --llm-cache outputs/llm_cache.jsonl --out …` |
| Cả chuỗi với mapping tay | `python -m datamate.eval.oracle --all --llm-url … --llm-cache outputs/llm_cache.jsonl --out …` (`--twin-threshold -1` để tắt cổng) |
| Chấm plan có sẵn | `python -m datamate.eval.check_plans --out outputs/check_plans/run.jsonl` |
| Dựng kho đã kiểm chứng | `python -m datamate.eval.build_bank [--llm-url …]` |
| So hai rulebook | `python -m datamate.rules diff data/train/rulebook.md data/public_test/rulebook.md` |
| Sinh lại danh sách cột của mapping tay (sau khi thêm mapping tay) | `python tools/mapping_signatures.py` |
| Đo nối tên | `python -m datamate.eval.linking [--llm-url …] --out outputs/linking/run.jsonl` |

## Git
Commit cuối là `49d8ea7`. Chưa commit: cổng thuật ngữ R46 (`rules`, `pipeline`, `decide`, `contracts/results`), `tests/test_rule_terms.py`, `tools/run_stats.py` và tài liệu. Lệnh cho trưởng nhóm:
```powershell
cd E:\ZAIC
git add datamate docs tests tools
git commit -m "Phiên 3: nộp public lần 1 (0.316) + 4 lượt chẩn đoán, R46 cổng thuật ngữ rulebook, tools/run_stats.py, bàn giao phiên 4"
git push origin main
```
