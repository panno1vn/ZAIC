# G4 — [C2] Tính ngày · [F] Format

## [C2] Temporal Engine
**Mục tiêu:** đổi kỳ dạng ký hiệu thành ngày cụ thể, đúng **từng dòng** rulebook §2.

**Hợp đồng:** `resolve(plan, as_of, calendar_csv, db) -> ResolvedPlan | None`. Điền `period`, `compare_period`, `series`. `mode = stock` cho kiểu `until`.

**Đã có (bộ khung 05/11):** `day`, `today`, `yesterday`, `month`, `quarter`, `year`; tháng/quý không ghi năm theo §2; kỳ phát sinh bị cắt tại `as_of_date`; kỳ nằm hẳn sau hôm nay thì trả `None`. Có `compare` hoặc `months` thì trả `None`.

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
