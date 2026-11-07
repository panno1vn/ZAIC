# Phân việc nhóm (08–16/11)

*Viết 07/11/2026. Docker nộp lần 1 ngày 14/11; đóng băng 16/11 23:59.*

## Hệ đang ở đâu
DataMate trả lời câu hỏi số liệu của cửa hàng theo năm bước:
1. đọc file của cửa hàng;
2. **map** về một schema chuẩn (`datamate/mapping/`);
3. LLM (Qwen3-8B qua llama-server) đọc câu hỏi thành một **plan** JSON (`datamate/nlu/`);
4. **hàm tính** đúng theo rulebook ra số (`datamate/metrics/`);
5. các **cổng** quyết định trả lời hay bỏ trống (`datamate/verify/`, `datamate/decide/`).

Đúng +1, sai −1, bỏ trống 0. Vì vậy hệ chỉ trả lời khi chắc.

| Thước đo | Giá trị |
|---|---|
| Public tốt nhất | **0,744** (773 đúng, 29 sai, 198 trống) |
| Ứng viên nộp kế | `outputs/replay/run11_s33` (821 câu trả lời) |
| Train | **2747 đúng / 0 sai / 253 trống** |
| Test | 466 qua |
| Lượt đủ 1000 câu có LLM | 38,7 phút trên laptop, 0 lỗi |

Lịch sử và lý do của từng quyết định: `docs/HAN_CHE_VA_CAI_THIEN.md` (mục N1–N75). Lượt nộp và điểm: `docs/CAN_XAC_MINH.md`.

## Cài đặt (ngày đầu, ai cũng làm)
1. Clone repo, tạo môi trường Python 3.10:
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt pytest
   ```
2. **Dữ liệu** không có trong repo. Tải từ trang BTC, đặt thành `data/train/` và `data/public_test/`; mỗi thư mục có `questions.jsonl`, `rulebook.md`, `calendar.csv`, `data/`.
3. **Gói `outputs`** (khoảng 11 MB, trưởng nhóm gửi): giải nén vào gốc repo, giữ nguyên cấu trúc `outputs/...`. Gói có:
   - cache LLM của bước map và kho plan, để đo train không cần server;
   - log của run11 và các lượt đọc lại;
   - bộ nộp chẩn đoán.
4. Kiểm, phải ra đúng các con số ở bảng trên:
   ```powershell
   .venv\Scripts\python.exe -m pytest -q
   .venv\Scripts\python.exe tools/eval_cached.py
   ```
   `eval_cached` mất khoảng 15 phút và phải in `đúng 2747 · sai 0`, `CACHE MISSES: 0`.
5. Việc nào cần LLM thì mở llama-server với model `Qwen3-8B-Q4_K_M.gguf` (cài đặt và lệnh ở `CAI_DAT.md`, bước 7). File model khoảng 5 GB: tải ở mạng mạnh.

## Luật bắt buộc (vi phạm có thể bị loại)
- Không có id cửa hàng hay id câu hỏi trong code, kể cả comment. `tests/test_no_id_logic.py` sẽ bắt.
- Không viết mapping, plan hay đáp án tay cho cửa hàng public. Không gán nhãn câu public.
- Xem dữ liệu public chỉ để tìm **kiểu** lỗi (định dạng, cách viết). Mọi bản sửa phải là quy tắc chung.
- Không dò đáp án từng câu bằng lượt nộp. Chỉ chẩn đoán theo nhóm lớn; công cụ chỉ in số đếm.
- Không gọi API ngoài khi dự đoán. Model ≤ 15B, công bố trước 26/10/2026. Thư viện phải có giấy phép OSI.

## Cách làm việc
- Mỗi task một nhánh `task/<số>-<tên>`; không commit thẳng vào `main`. Mở PR, trưởng nhóm duyệt và merge.
- Mỗi bản sửa cần:
  - **test**;
  - **một mục trong `docs/HAN_CHE_VA_CAI_THIEN.md`**: vấn đề, căn cứ (số liệu), cách sửa, kết quả;
  - số đo trước / sau trong mô tả PR.
- Đổi `datamate/mapping/`, `datamate/metrics/` hay `datamate/nlu/` thì phải chạy `tools/eval_cached.py`: **0 sai, không giảm số đúng, CACHE MISSES 0**. Ra CACHE MISSES > 0 nghĩa là prompt hoặc schema của câu train đã đổi, phải đo lại có server, nên tránh.
- Đo tác động trên public không cần LLM:
  ```powershell
  .venv\Scripts\python.exe tools/replay_run.py outputs/public_run11 --out outputs/replay/<tên> [--enrich]
  .venv\Scripts\python.exe tools/compare_runs.py outputs/replay/<tên> outputs/replay/run11_s33/submission.jsonl
  ```
  Thêm `--enrich` khi sửa phần bổ sung mapping từ README.

## Mốc
| Ngày | Việc |
|---|---|
| 08/11 | cài đặt theo CAI_DAT.md, ra đúng số; đọc tài liệu của task |
| 09/11 tối | mỗi người gửi ghi chú nghiên cứu ngắn: trả lời các câu hỏi ở mục "Tự nghiên cứu", và định làm gì |
| 10–12/11 | làm, mở PR |
| **12/11 22:00** | **hạn merge cho Docker lần 1**: chỉ PR đã merge và đủ số đo mới vào image |
| 13/11 | Task 1 build và chạy thử image |
| 14/11 | nộp Docker |
| 15–16/11 | chỉ sửa nhỏ có test; đóng băng 16/11 23:59 |

---

## Task 1: Docker và quy trình nộp (hạn cứng 14/11)
**Người nhận:** ____

**Mục tiêu.** Một image chạy trên máy chấm không có mạng (2× RTX 5090, tối đa 6 giờ), ghi `/result/submission.jsonl` hợp lệ. Kết quả gần như trùng run11, và có quy trình nộp rõ ràng.

**Căn cứ.**
- run11 chạy 38,7 phút trên laptop, 0 lỗi.
- Code đã chạy được từ một bản chép chỉ có `datamate/`, `assets/`, `configs/`, đúng ba thư mục Dockerfile chép vào image.
- Bản nháp Dockerfile và `predict.sh` đã có nhưng **chưa build lần nào**.

**Đọc trước.** `docker/README.md`, `docker/Dockerfile`, `docker/predict.sh`, `docker/README_IMAGE.md`, `datamate/predict.py`, `configs/default.json` (ngân sách thời gian).

**Tự nghiên cứu.**
- BTC đã có Docker guideline 2026 chưa? Cần biết base image, đường dẫn `/data` và `/result`, lệnh chạy, cách nộp (dung lượng, Drive, form). Nếu chưa có, dùng guideline 2025 làm mẫu và ghi các điểm có thể khác.
- llama.cpp bản `b12064` build cho RTX 5090 (sm_120, CUDA 12.8) có vấn đề gì không? Thời gian nạp model và VRAM dùng bao nhiêu?
- Máy chấm có 2 GPU. Có nên chạy 2 server hoặc `--parallel` không? Không bắt buộc, vì 40 phút còn xa 6 giờ: **ổn định quan trọng hơn nhanh**.
- Giấy phép của Qwen3, llama.cpp và các thư viện Python, để điền vào `README_IMAGE.md`.
- `docker save`, nén, `sha256sum`: image nặng bao nhiêu, tải lên mất bao lâu?

**Xong khi.**
1. `docker run --network none --gpus all -v <data>:/data:ro -v <result>:/result` chạy hết public.
2. `tools/compare_runs.py <result> outputs/public_run11/submission.jsonl` cho thấy khác khoảng 1% trở xuống. LLM tự nó dao động cỡ 8/1000 câu giữa hai lượt.
3. Thời gian nạp model và thời gian dự đoán được ghi vào `docker/README.md`.
4. Có checklist nộp từng bước.

**Phạm vi file.** `docker/*`, `.dockerignore`; `requirements.txt` chỉ khi thật cần.

**Lưu ý.** Không build trên laptop dùng 4G. Thuê **VM** có GPU (container thuê không chạy được Docker bên trong); hỏi trưởng nhóm duyệt chi phí. Tải model ngay trên VM. Build lại image sau hạn merge 12/11.

---

## Task 2: Chẩn đoán public, săn kiểu câu sai
**Người nhận:** ____ (giữ việc nộp bài cùng trưởng nhóm: 5 lượt một ngày)

**Mục tiêu.** Dùng lượt nộp để khoanh vùng 29 câu sai của lượt 0,744 và đo các bản sửa mới. Tìm **kiểu** sai rồi đề xuất quy tắc chung.

**Căn cứ.**
- Chẩn đoán 07/11: so sánh 3/73 sai, xếp hạng 4/70, **đếm theo ngưỡng 6/58** (nhiều nhất), một số có bộ lọc 4/72.
- **12 câu sai** chưa biết nằm ở đâu trong 529 câu.
- Bộ nộp kế tiếp đã dựng sẵn: `outputs/public_ablation12/`.

**Đọc trước.** `docs/CAN_XAC_MINH.md` (công thức: sai của nhóm = (số câu − (điểm lượt đủ − điểm lượt bỏ nhóm) × 1000) / 2), `tools/ablate_groups.py`, `tools/ablate.py`, `tools/run_stats.py`. Trong HAN_CHE, mục N57 và N58 là ví dụ tìm kiểu lỗi định dạng: năm hai chữ số "th 6/25" làm 14 câu lệch một năm.

**Tự nghiên cứu.**
- Thiết kế cách chia đôi nhóm (bỏ trống nửa nhóm mỗi lượt) để khoanh 12 câu sai về nhóm nhỏ trong ít lượt nhất. Nhóm phải đủ lớn, vì luật cấm dò từng câu.
- Với nhóm sai nhiều nhất: hình dạng plan (thực thể, phép so, ngưỡng, kỳ) và cách viết câu nào public có mà train không có?
- Public còn định dạng nào chưa xử lý? Đã gặp: "M/YY", "T5/2025", "đh", "o đờ", "10 củ", "từ hồi X lên giá Y". Hãy rà bằng regex trên 1000 câu và đếm theo hình dạng.

**Xong khi.** Mỗi ngày nộp đủ lượt và ghi kết quả vào `CAN_XAC_MINH.md`. Có ít nhất một kiểu sai được sửa bằng quy tắc chung, có test, train vẫn 0 sai.

**Phạm vi file.** `tools/ablate*.py`, `docs/CAN_XAC_MINH.md`, `datamate/nlu/grounding.py` (cổng và viết lại plan).

**Lưu ý.** Câu sai khiến điểm giảm. Một nhóm chỉ đáng chặn khi số câu sai **nhiều hơn** số câu đúng; sai 20–50% thì giữ lại và tìm kiểu sai.

---

## Task 3: Mapping: bảng phụ bị bỏ sót khi chuyển từ mẫu
**Người nhận:** ____

**Mục tiêu.** Một cửa hàng map theo mẫu ít bảng không được mất sổ nhập, danh mục hay sổ nợ mà README có mô tả.

**Căn cứ (N72).**
- dev_007 và dev_008 có file nhập hàng và danh mục, nhưng mapping chỉ có đơn và dòng hàng. Nguyên nhân: mẫu được chọn (biz_101) chỉ có một file, và `sibling_files` xếp mẫu theo tỉ lệ bảng **của mẫu** ghép được.
- Hậu quả: 5 câu về nhập hàng bỏ trống, và trước N73 còn mất cả giờ đặt đơn.
- dev_008 ghi nợ trong ô Note (245 đơn), chỉ có tình trạng cuối dữ liệu, không có ngày trả.

**Đọc trước.**
- `datamate/mapping/transfer.py`: `map_by_transfer`, `sibling_files`, `pair_tables`.
- `datamate/mapping/from_readme.py`:
  - `enrich`;
  - `_purchases`;
  - `with_order_hour` (N73): mẫu của một bổ sung có kiểm chứng.
- `datamate/mapping/side_books.py` (N68).
- HAN_CHE N27, N29, N68, N73.

**Tự nghiên cứu.**
- **Hướng A, không cần LLM:** cho `enrich` thêm bảng `purchases` / `products` dựng từ README khi mapping còn thiếu. `from_readme` đã dựng được các bảng này cho mapping làm từ README. Điều kiện gì đảm bảo ghép đúng (khoá mặt hàng của sổ nhập phải khớp khoá trên dòng bán)? Thử trên những cửa hàng train nào?
- **Hướng B:** xếp mẫu theo số file **của cửa hàng** được dùng. Mapping của bao nhiêu cửa hàng train và public sẽ đổi? Cách này cần llama-server và rủi ro hơn.
- Nợ ghi trong Note: §4 cho tính được gì khi chỉ có tình trạng cuối? Có lẽ chỉ câu hỏi đúng ngày cuối dữ liệu.

**Xong khi.** `eval_cached` ≥ 2747 đúng, 0 sai, CACHE MISSES 0. Đọc lại public bằng `--enrich` cho thấy câu nào đổi và vì sao. Có test cho mỗi đường mới.

**Phạm vi file.** `datamate/mapping/*`.

**Lưu ý.** Hướng B đổi mapping của cả những cửa hàng đang trả lời tốt. Làm hướng B thì phải chạy lại LLM cho các cửa hàng đó (`tools/run_shops.py`) và so từng câu.

---

## Task 4: Hàm tính còn thiếu
**Người nhận:** ____

**Mục tiêu.** Thêm hàm cho các khái niệm rulebook chưa có hàm. Mỗi công thức phải được kiểm bằng đáp án train **trước** khi viết.

**Căn cứ (N72).**
- 19 câu public bỏ trống vì "chưa có hàm".
- 6 câu xếp hạng tăng dần ("bán ít nhất").
- 3 câu giá trị đơn trung bình hoặc số đơn huỷ có lọc theo mặt hàng.
- Dòng rulebook chưa có hàm nào dẫn tới:
  - §5 nhập trừ bán (2 câu public "số viên nhập trừ số viên bán");
  - §5 giá trị hàng tồn kho theo giá vốn danh mục (có câu train ở biz_124);
  - §5 giá vốn;
  - §1 báo cáo tiền mặt theo ca;
  - §3 ngày đắt khách nhất;
  - §6 topping ghi chung ô với món.

**Đọc trước.**
- `datamate/metrics/registry.py`, `sales.py`, `stock.py`.
- **`lots.py` (N74), mẫu nên theo**: kiểm công thức bằng một nguồn khác ngay trong dữ liệu (tồn theo lô cộng lại = thẻ kho 80/80 mặt hàng) rồi mới đối chiếu đáp án train.
- `datamate/contracts/plan.py` (danh sách chỉ số và điều kiện).
- `data/*/rulebook.md`.

**Tự nghiên cứu.**
- Lập danh sách khoá thiếu hàm: đọc lại run11 bằng `tools/replay_run.py`, rồi chạy `tools/run_stats.py` lên lượt đó (mục "hàm không ra kết quả, theo lý do").
- Với mỗi khái niệm: câu train nào hỏi (tìm theo từ khoá và theo plan trong `outputs/bank/llm_plans.jsonl`), đáp án là gì? Công thức nào ra đúng **mọi** câu đó?
- Xếp hạng tăng dần: mặt hàng bán 0 có được tính không, rulebook nói gì? Train có câu nào?

**Xong khi.** Mỗi hàm có test với số tính tay và khớp đáp án train. `eval_cached` 0 sai, số đúng không giảm.

**Phạm vi file.** `datamate/metrics/*`: một nhóm khái niệm mới thì đặt vào file mới, như `lots.py`.

**Lưu ý.** Không đổi schema hay prompt: đổi là cache LLM không còn khớp. Thiếu dữ liệu thì trả `None` (bỏ trống), không đoán.

---

## Task 5: Sẵn sàng cho private: luật đổi, unanswerable, LLM đọc hỏng
**Người nhận:** ____

**Mục tiêu.** Private có cửa hàng lạ và rulebook có thể khác. Hệ không được sai hàng loạt khi luật đổi, và không được bỏ trống những câu có thể trả "không trả lời được".

**Căn cứ.**
- So với train, rulebook public đã bỏ 3 dòng (giá nhập bình quân, tồn theo đơn vị lớn, giá bán ngày D) và thêm nhiều dòng theo ngành. Khi một dòng luật đổi, `[R]` hạ độ tin cậy hoặc chặn câu.
- Unanswerable mới bật nhóm A (kỳ hỏi nằm ngoài dữ liệu, N28). Train còn 44 câu unanswerable khác chưa bật, chủ yếu nhóm B: cửa hàng không ghi loại thông tin đó.
- Mỗi lượt có khoảng 3 lỗi gọi LLM (`JSONDecodeError`) và 11 đầu ra sai schema không sửa được.

**Đọc trước.** `datamate/rules/__init__.py` (`check_rules`, `new_terms`, `unverified_terms`), `datamate/verify/`, `datamate/decide/`, `datamate/nlu/repair.py`, `datamate/llm/` (`max_tokens` = 1024). HAN_CHE N28, N32, N37, N53.

**Tự nghiên cứu.**
- `.venv\Scripts\python.exe -m datamate.rules diff data/train/rulebook.md data/public_test/rulebook.md` so rulebook train với public: dòng nào chỉ đổi **tham số** (giờ của ca, ngưỡng "từ 3 đơn")? Hàm nào đang viết cứng tham số đó? Đọc tham số từ rulebook có an toàn không?
- Unanswerable nhóm B: trên train, câu nào có tín hiệu rõ (cột cần không có trong mapping)? Trước khi bật, đo xem train ra bao nhiêu đúng, bao nhiêu sai; không được có câu sai.
- `JSONDecodeError`: đầu ra bị cắt vì `max_tokens`, hay Qwen3 sinh phần "thinking"? Xem `reading` trong `outputs/public_run11/logs/q_*.json`.
- (Tuỳ chọn) dữ liệu tổng hợp ngành mới để thử mapping. Chỉ dùng lúc phát triển.

**Xong khi.** Mỗi thay đổi đã đo trên train (0 sai) và đọc lại trên public, có test.

**Phạm vi file.** `datamate/rules/`, `datamate/verify/`, `datamate/decide/`, `datamate/nlu/repair.py`, `datamate/llm/`.
