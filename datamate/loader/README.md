# G1 — [A] Đọc + làm sạch, [A2] Profiling

**Mục tiêu:** đọc được **mọi** file của **mọi** cửa hàng, kể cả kiểu file chưa từng thấy ở bộ private, ra các bảng thô có header đúng.

**Hợp đồng:** `load_business(thư mục) -> RawBusiness`, `profile_business(raw) -> BusinessProfile` ([contracts/raw.py](../contracts/raw.py)). Đọc ở chế độ chỉ đọc, không ghi gì vào thư mục dữ liệu.

**Đã có (03/11, xong G1 bản 1):**
- [__init__.py](__init__.py): đọc csv (tự dò dấu phân cách `,` `;` tab; không phải UTF-8 thì thử cp1258), **mọi sheet xlsx** bằng `python-calamine` (MIT, nhanh hơn openpyxl nhiều lần), sqlite (NULL thành ô trống). Đọc cả thư mục con. File lạ thì bỏ qua và ghi cảnh báo. Mỗi cửa hàng đọc tối đa `BUDGET_S` = 300 giây (H12, phần đọc file).
- [grid.py](grid.py):
  - đổi mọi ô sang text: số nguyên lưu dạng float bỏ `.0`; ngày ra ISO;
  - dò header: dòng đầu tiên rộng gần bằng dữ liệu và toàn là tên;
  - bỏ dòng tiêu đề phía trên header; nhận dòng nhóm cột của header 2 dòng và ghi vào `notes`;
  - đặt tên cột trùng `_2`, `_3`; bỏ cột trống;
  - **bỏ dòng tổng** "Cộng" / "Tổng cộng" (H18; dòng có ít ô, nên khách tên "Tống…" không bị bỏ);
  - `year_hint` từ tên sheet, không có thì từ tên file.
- [parse.py](parse.py): thêm các kiểu tiền thấy trong dữ liệu: `1tr440`, `409tr663`, `45,000.0000`, `1.234,50`. `parse_number` dùng cùng quy tắc dấu phân cách. Trước đây `45,000.0000` bị đọc **sai lặng lẽ** thành 45.
- `profile_business`: đoán kiểu cột (date / money / number / text / empty), min / max.
- Test: [tests/test_loader.py](../../tests/test_loader.py).

**Kết quả trên dữ liệu thật (03/11):**
- 44/44 cửa hàng đọc không lỗi, không cảnh báo; đọc hết train khoảng 150 giây, chậm nhất 16 giây/cửa hàng.
- Header 2 dòng đúng ở biz_105, biz_117, dev_004, dev_013.
- Dòng tổng bị bỏ ở 3 cửa hàng (biz_105, dev_004, dev_014): 50 dòng, đều là "Cộng / Tổng cộng / Tong cong + một con số".

**Còn lại (làm khi cần):**
- Đoán kiểu cột không phân biệt được ngày dạng serial Excel (`45689`) với giá tiền 5 chữ số; mapping phải dựa vào tên cột và mẫu giá trị.
- Đọc hết train mất ~2,5 phút, chậm hơn mục tiêu 2 phút, nhưng không đáng kể so với giới hạn 6 giờ. Muốn nhanh hơn thì tối ưu vòng `cell_text`.
- Một file đơn lẻ rất lớn vẫn có thể đọc quá `BUDGET_S`, vì giới hạn chỉ được kiểm giữa các file.

**Thế nào là xong:**
- [x] Đọc 44 cửa hàng không lỗi và không thiếu sheet.
- [x] Header đúng ở 4 cửa hàng có header 2 dòng.
- [x] `python -m pytest` qua hết.

**Chạy thử:** `python -m datamate.eval.oracle --business biz_101 --out outputs/oracle_biz101`. Đọc log `_business_*.json` để xem cảnh báo.

**Đọc thêm:** [docs/research/entities.md](../../docs/research/entities.md), rulebook §8, README các cửa hàng.
