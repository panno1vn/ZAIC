# G4 — [C2] Tính ngày · [F] Format

## [C2] Temporal Engine
**Mục tiêu:** đổi kỳ dạng ký hiệu thành ngày cụ thể, đúng **từng dòng** rulebook §2.

**Hợp đồng:** `resolve(plan, as_of, calendar_csv, db) -> ResolvedPlan | None`. Điền `period`, `compare_period`, `series`. `mode = stock` cho kiểu `until`.

**Đã có (05/11, G4 bản 1):**
- **Mọi kiểu kỳ** của hợp đồng v1.1 và **mọi kiểu so sánh**.
- Tết tra `calendar.csv`: Tết 2025, 2026, 2027 đều dài 17 ngày, khớp câu train "17 ngày trước Tết". `compare.n` không khớp độ dài kỳ thì bỏ trống.
- Chỉ số trong `STOCK_METRICS` luôn tính kiểu `stock`.
- `previous` của tháng này, hoặc của tháng đang dở, lấy cùng số ngày. Kiểu kỳ không có "kỳ trước" rõ ràng (từ đầu năm, chuỗi tháng) thì bỏ trống.
- Test theo từng dòng §2: [tests/test_temporal.py](../../tests/test_temporal.py).
- Trên 123 plan viết tay: tính được kỳ cho 122.
- **Còn thiếu:** `days_from` neo theo ngày tăng giá (`anchor_price`). Phần này cần mặt hàng đã được nối tên, nên làm cùng các hàm hiệu ứng tăng giá (11/11).

Các mục 1–3 dưới đây đã làm, trừ `anchor_price`.

**Việc cần làm:**
1. Các kiểu kỳ còn lại: `this_week`, `last_week` (thứ Hai–Chủ nhật), `this_month`, `last_month`, `ytd`, `last_n_days`, `next_n_days`, `range` (ngày hoặc tháng), `months` (danh sách hoặc `end` + `n`), `until` (`mode = stock`), `tet` (tra `calendar.csv`: 23 tháng Chạp → hết mùng 10 Giêng), `days_from` (có ngày, hoặc `anchor_price`: tìm ngày tăng giá trong `db.tables["price_history"]`).
2. Kỳ so: `previous`, `previous_same_days` (tháng trước không có ngày đó thì lấy tới hết tháng), `same_period_last_year`, `before_tet`, `before_days_from`, `period`.
3. Hợp đồng v1.1 (K2):
   - Chỉ số trong `STOCK_METRICS` luôn tính theo `mode = stock` (từ đầu dữ liệu đến hết ngày), kể cả khi kỳ là `today` hoặc để trống.
   - `tet` không có `lunar_year` nghĩa là Tết năm nay. So sánh `same_period_last_year` với kỳ Tết là so với Tết năm âm trước, không phải cùng ngày dương lịch.
   - `expiring_within` không có `n` thì lấy `period` làm khoảng hạn dùng.
4. Mỗi dòng của §2 viết ít nhất một test, có cả các ví dụ trong sổ tay nhóm (ví dụ tuần trước của ngày 27/08/2026 là 17–23/08).

## [F] Format
**Đã có:** [formatter/](../formatter/__init__.py). Làm tròn nửa lên (`money`, `round_half_up`); format number, percent, list, table; giá trị sai format thì bỏ trống.

**Việc cần làm:** đối chiếu từng dòng §9; table đúng thứ tự cột theo câu hỏi; tồn theo đơn vị lớn ra `[lớn, lẻ]`; câu hỏi theo tháng ra `YYYY-MM`.

**Thế nào là xong:** mỗi dòng §2 và §9 có test qua.

**Đọc thêm:** [docs/research/periods.md](../../docs/research/periods.md), rulebook §2, §9.
