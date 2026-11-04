# G3 — [C] Hiểu câu hỏi · G6 — [C3] Nối thực thể

## G3: [C] Question Understanding
**Mục tiêu:** chuyển câu hỏi tiếng Việt (không dấu, viết tắt, gõ sai) thành `QueryPlan` đúng.

**Hợp đồng:** `parse_question(câu hỏi, as_of, card, llm) -> QueryPlan | None` ([contracts/plan.py](../contracts/plan.py)). Không đọc được thì trả `None`.

**Đã có (bộ khung 05/11):** [baseline.py](baseline.py), bộ hiểu câu hỏi theo luật cho 4 dạng câu (doanh thu, số đơn, mặt hàng bán chạy nhất, ngày doanh thu cao nhất) với 4 kiểu kỳ. Gặp từ lạ là trả `None`, để **không bao giờ đoán bộ lọc**. Trên biz_101 trả lời được 28/40 câu, không câu nào sai.

**Đã có (04/11, phần K3 không cần GPU):**
- [llm/__init__.py](../llm/__init__.py) `LlamaServerLLM`: gọi `llama-server` của llama.cpp trên localhost (chạy offline được), temperature 0, seed cố định, ép output theo JSON schema, **timeout cho mỗi lời gọi** (H12), tắt chế độ thinking của Qwen3 (server cần cờ `--jinja`).
- [prompt.py](prompt.py): hướng dẫn ngắn bám hợp đồng v1.1 (kèm các mã bộ lọc), data card, 6 ví dụ mẫu chọn bằng BM25 trên kho 123 plan viết tay; tổng khoảng 1.500 token.
- `parse_question` với LLM: plan phải hợp lệ; baseline cũng đọc được câu đó thì hai bên phải ra plan giống nhau (`canonical_plan`), khác thì trả `None`.
- Lệnh chấm K3: `python -m datamate.eval.k3 --base-url http://127.0.0.1:8080 --out outputs/k3/x.jsonl`. Mỗi câu bị loại khỏi kho ví dụ của chính nó. Có `--mock` để tự kiểm tra: ra 100%.
- **K3 (05/11) với Qwen3-8B Q4_K_M: plan khớp hoàn toàn 83,7%, 1,8 giây/câu, chạy lại ra y hệt.** Chi tiết ở mục K3 trong file hạn chế. Hai bước sau K3:
  - `PLAN_SCHEMA` là **schema sinh output**: `anyOf` theo loại câu, các trường bắt buộc theo thứ tự đọc, `filters` bắt buộc. Hợp đồng `QueryPlan` vẫn là nơi kiểm tra cuối cùng.
  - [grounding.py](grounding.py): bộ lọc phải có căn cứ trong câu hỏi, không có thì plan bị loại.
- Chạy server: `llama-server -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091`. Cổng 8080 trên laptop từng bị chiếm, nên dùng 8091.

**Việc cần làm:**
1. Backend LLM thật trong [datamate/llm](../llm/__init__.py): chạy model local, temperature 0, **timeout cho mỗi lời gọi** (mục H12), ép output theo JSON schema `schemas/query_plan.schema.json`.
2. Prompt gồm schema, data card và 5–8 ví dụ mẫu gần nhất (BM25 trên [assets/plans/](../../assets/plans/)). Mục K3: thử trên 30 câu train với Qwen3-8B trước.
3. Prompt phải ghi rõ các **mã** của bộ lọc (ca, thứ, trạng thái, kê đơn: `CODED_VALUES`, đã có trong mô tả của schema) và nhắc rằng trường lạ làm plan bị từ chối. Khi bật structured output, schema đã có `additionalProperties: false`.
   - Ví dụ mẫu có thêm 99 plan viết tay của K2 ([assets/plans/k2_trial.jsonl](../../assets/plans/k2_trial.jsonl)). Các plan này mới đúng hợp đồng, **chưa kiểm chứng bằng đáp án**; chỉ đưa vào kho ví dụ sau khi chạy ra đúng đáp án (mục K1).
4. Đối chiếu với `baseline`: hai bên cùng parse được mà khác nhau thì trả `None`.
5. Kho ví dụ đã kiểm chứng: cho LLM parse cả 3000 câu train, chỉ giữ plan chạy ra đúng đáp án.
6. (Nếu kịp) [D2] sinh code: [codegen/](../codegen/__init__.py).

**Thế nào là xong:** tỉ lệ plan đúng trên tập train chia theo ngành (leave-one-industry-out); PA trên train không giảm khi bật LLM.

## G6: [C3] Nối thực thể
**Mục tiêu:** đổi giá trị bộ lọc viết trong câu ("coca", "cafe sua M", "Hai Bà Trưng") thành giá trị có thật trong dữ liệu.

**Hợp đồng:** `link_entities(resolved, db, question) -> ResolvedPlan`. Ghi `linked[giá trị như trong câu] = giá trị để lọc` và `link_scores`. Không chắc thì **không ghi**; [V] sẽ cho câu đó bỏ trống.

**Đã có (T2, phiên 3, 03/11):** [linking.py](linking.py). Chi tiết và số đo ở [docs/research/linking.md](../../docs/research/linking.md).
- Ba bước: khớp tuyệt đối (cả mã) → tên đầy đủ có trong câu hỏi → so khớp mờ `token_sort_ratio` ≥ 90, hơn ứng viên thứ hai ≥ 5 điểm.
- Tên hàng nối về **mã hàng**. Tên hàng được thử thêm sau khi bỏ đơn vị đếm ở đầu.
- Kênh bán và thanh toán nối về **mã** qua [assets/linking/synonyms.json](../../assets/linking/synonyms.json). Lọc bằng `linking.matches`, vì có cột trộn mã với chữ.
- Trên 220 câu train có bộ lọc của 8 cửa hàng: nối được 100% tên hàng, 94% tên khách. Mọi tên không nối được đều thuộc câu `unanswerable`.

**Việc cần làm:**
1. ~~So khớp không dấu bằng RapidFuzz; chấp nhận cả mã.~~ Xong.
2. ~~Ngưỡng; hai ứng viên gần bằng nhau thì không nối.~~ Xong.
3. Tên khách viết khác cách là cùng một khách (§3). Phần này ở mapping (G2): shop không có mã khách thì `customer_key` = tên đã chuẩn hoá. Linking chỉ nối về `customer_key`.
4. T3: đo "câu đã nối mà trả lời sai = 0" bằng đáp án.

**Thế nào là xong:** trên các câu train có bộ lọc, nối đúng ≥ 95% ở những câu đã nối, và có số đo tỉ lệ không nối được.

**Đọc thêm:** [docs/research/intents.md](../../docs/research/intents.md), [docs/contracts.md](../../docs/contracts.md).
