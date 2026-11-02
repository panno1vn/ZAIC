# G1 — [A] Đọc + làm sạch, [A2] Profiling

**Mục tiêu:** đọc được **mọi** file của **mọi** cửa hàng, kể cả kiểu file chưa từng thấy ở bộ private, ra các bảng thô có header đúng.

**Hợp đồng:** `load_business(thư mục) -> RawBusiness`, `profile_business(raw) -> BusinessProfile` ([contracts/raw.py](../contracts/raw.py)). Đọc ở chế độ chỉ đọc, không ghi gì vào thư mục dữ liệu.

**Đã có (bộ khung 05/11):**
- Đọc csv và sqlite thành text.
- Các hàm parse trong [parse.py](parse.py) đã có test: tiền `25k`, `30.500đ`, `560,000`; ngày dạng serial Excel, `1 thg 6 2025`, `1/6` cộng năm của sheet; số lượng `5 chai`.
- Profiling cơ bản: tên cột, vài giá trị mẫu.

**Việc cần làm (theo thứ tự):**
1. Đọc xlsx: mọi sheet, mỗi sheet một `RawTable` với `table_id = "file::sheet"`; ô giữ dạng text.
2. Dò dòng header: có dòng tiêu đề phía trên; header gộp 2 dòng (biz_105, biz_117, dev_004, dev_013). Tên cột trùng thì thêm hậu tố.
3. Điền `RawTable.year_hint` từ tên sheet (`Thang 06 2026`, `T06-2026`, `T7-2025`) hoặc tên file (`BanHang_T11_2025`).
4. Profiling đầy đủ: đoán kiểu cột (tiền, số, ngày, text), min/max, khoảng ngày.
5. Bổ sung hàm parse cho các kiểu mới gặp; mỗi kiểu một test.
6. Đặt giới hạn thời gian đọc mỗi cửa hàng (mục H12).

**Thế nào là xong:**
- Đọc 44 cửa hàng không lỗi và không thiếu sheet.
- Header đúng ở 4 cửa hàng có header 2 dòng.
- `python -m pytest` qua hết.

**Chạy thử:** `python -m datamate.eval.oracle --business biz_101 --out outputs/oracle_biz101`. Đọc log `_business_*.json` để xem cảnh báo.

**Đọc thêm:** [docs/research/entities.md](../../docs/research/entities.md), rulebook §8, README các cửa hàng.
