# G3 — [C] Hiểu câu hỏi · G6 — [C3] Nối thực thể

## G3: [C] Question Understanding
**Mục tiêu:** chuyển câu hỏi tiếng Việt (không dấu, viết tắt, gõ sai) thành `QueryPlan` đúng.

**Hợp đồng:** `parse_question(câu hỏi, as_of, card, llm) -> QueryPlan | None` ([contracts/plan.py](../contracts/plan.py)). Không đọc được thì trả `None`.

**Đã có (bộ khung 05/11):** [baseline.py](baseline.py), bộ hiểu câu hỏi theo luật cho 4 dạng câu (doanh thu, số đơn, mặt hàng bán chạy nhất, ngày doanh thu cao nhất) với 4 kiểu kỳ. Gặp từ lạ là trả `None`, để **không bao giờ đoán bộ lọc**. Trên biz_101 trả lời được 28/40 câu, không câu nào sai.

**Việc cần làm:**
1. Backend LLM thật trong [datamate/llm](../llm/__init__.py): chạy model local, temperature 0, **timeout cho mỗi lời gọi** (mục H12), ép output theo JSON schema `schemas/query_plan.schema.json`.
2. Prompt gồm schema, data card và 5–8 ví dụ mẫu gần nhất (BM25 trên [assets/plans/](../../assets/plans/)). Mục K3: thử trên 30 câu train với Qwen3-8B trước.
3. Đối chiếu với `baseline`: hai bên cùng parse được mà khác nhau thì trả `None`.
4. Kho ví dụ đã kiểm chứng: cho LLM parse cả 3000 câu train, chỉ giữ plan chạy ra đúng đáp án.
5. (Nếu kịp) [D2] sinh code: [codegen/](../codegen/__init__.py).

**Thế nào là xong:** tỉ lệ plan đúng trên tập train chia theo ngành (leave-one-industry-out); PA trên train không giảm khi bật LLM.

## G6: [C3] Nối thực thể
**Mục tiêu:** đổi giá trị bộ lọc viết trong câu ("coca", "cafe sua M", "Hai Bà Trưng") thành giá trị có thật trong dữ liệu.

**Hợp đồng:** `link_entities(resolved, db) -> ResolvedPlan`. Ghi `linked[giá trị như trong câu] = giá trị trong dữ liệu` và `link_scores`. Không chắc thì **không ghi**; [V] sẽ cho câu đó bỏ trống.

**Việc cần làm:**
1. So khớp không dấu bằng RapidFuzz trên danh sách giá trị (tên hàng, nhóm, kênh, khách…); chấp nhận cả mã.
2. Đặt ngưỡng; hai ứng viên gần bằng nhau thì không nối.
3. Tên khách viết khác cách là cùng một khách (§3).

**Thế nào là xong:** trên các câu train có bộ lọc, nối đúng ≥ 95% ở những câu đã nối, và có số đo tỉ lệ không nối được.

**Đọc thêm:** [docs/research/intents.md](../../docs/research/intents.md), [docs/contracts.md](../../docs/contracts.md).
