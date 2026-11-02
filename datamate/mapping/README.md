# G2 — [B] Mapping về schema chuẩn

**Mục tiêu:** tự động map dữ liệu của **cửa hàng chưa từng thấy** về schema chuẩn. Map sai thì phải bị phát hiện, để cửa hàng đó bỏ trống thay vì trả lời sai.

**Hợp đồng:** `map_business(raw, profile, rulebook, llm) -> Mapping` ([contracts/mapping.py](../contracts/mapping.py)). `build_canonical(raw, mapping) -> CanonicalDB`; `run_checks(db)` chạy 6 bước kiểm tra bắt buộc (`REQUIRED_CHECKS`); `build_card(db) -> DataCard`.

**Đã có (bộ khung 05/11):**
- `build_canonical` ([build.py](build.py)): parse theo kiểu, đổi tên cột, `value_maps`, hằng số, bỏ dòng trùng trong cùng đơn (§8), mỗi đơn lấy dòng đầu, khoảng ngày theo bảng.
- `run_checks`: 6 bước kiểm tra bắt buộc (giải quyết mục H8; bước 6 "cột bắt buộc đủ giá trị" thêm ở review lần 2, mục R18): một ô ngày hay ô tiền không đọc được là cả cửa hàng không đạt, vì nếu bỏ qua thì đáp án sai mà không báo lỗi. Xem `detail` của bước đó để biết cột nào, bao nhiêu ô.
- **Chưa có kiểm tra theo nghĩa** (mục H17): map nhầm `line_amount` sang cột đơn giá vẫn qua đủ 6 bước.
- Mapping tay của biz_101: [assets/mappings/train/biz_101.json](../../assets/mappings/train/biz_101.json).
- `map_business` **chưa có**: hiện mọi cửa hàng đều bỏ trống.

**Việc cần làm:**
1. Cài 8 biến đổi trong `contracts.mapping.TRANSFORMS` (`regex_extract`, `split_qty_unit`, `year_from_sheet`, `note_contains`, `lookup`, `order_status_from_lines`, `concat`, `negate`).
2. Điền ô trống trong nhóm dòng của cùng một đơn (§8); dùng `year_hint` khi parse ngày.
3. Mapping tay cho 8 cửa hàng train khác kiểu nhau (từ data card của nhóm), lưu ở `assets/mappings/train/`.
4. `map_business`: luật đồng nghĩa tên cột trước, LLM điền phần còn thiếu (theo [schemas/mapping.schema.json](../contracts/schemas/mapping.schema.json)), chạy kiểm tra, sai thì cho LLM sửa một lần.
5. Nhận diện ngành (§6); bảng quy đổi đơn vị; bảng lạ vào `extra_tables`.

**Thế nào là xong:**
- Với các cửa hàng có mapping tay: chạy bình thường (mapping tự động) ra **cùng điểm** với `python -m datamate.eval.oracle`.
- Không cửa hàng nào qua kiểm tra mà map sai.

**Đọc thêm:** [docs/contracts.md](../../docs/contracts.md), [docs/research/entities.md](../../docs/research/entities.md), rulebook §6, §8.

**Luật thi:** mapping tay chỉ làm cho cửa hàng **train**. Không viết code riêng cho từng cửa hàng.
