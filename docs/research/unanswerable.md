# 70 câu unanswerable trong train

Đọc và phân loại tay cả 70 câu. Ba nhóm lý do:

| Nhóm | Số câu | Lý do cụ thể | Ví dụ |
|---|---:|---|---|
| **A. Kỳ hỏi nằm ngoài dữ liệu** | 18 | kỳ hỏi, hoặc **kỳ so**, trước ngày đầu tiên có dữ liệu (2 câu chưa chắc là lý do này hay thiếu nhập hàng / giá vốn) | "dthu thang 2/2025 bnhiu"; "so vs thang lien trc, doanh thu thang 4 nam 2025 thay doi bao nhieu %" (tháng 3/2025 không có dữ liệu) |
| **B. Shop không ghi loại thông tin đó** | 45 | | |
| | 10 | không có tồn kho / giá vốn | "het hom nay, bia tiger 330ml con lai may lon trong kho ha" |
| | 6 | không có địa chỉ khách | "Có bao nhiêu khách hàng ở đường Trần Não?" |
| | 6 | không có thông tin khách (không có tên/mã khách) | "bn khach mua it nhat 14 don trong thang 12 nam 2025" |
| | 5 | không có công nợ | "liệt kê 3 khách nợ nhiều nhất tính đến hết ngày 24/06/2026" |
| | 4 | không có giới tính khách | "trong thang 5/2026, khach nu chiem bnhiu % doanh thu" |
| | 4 | không có nhập hàng | "Cho hỏi tổng tiền nhập hàng tháng này là bao nhiêu?" |
| | 4 | không có kênh bán / hình thức thanh toán | "dthu các đơn trả bằng COD và doanh thu các đơn trả bằng tiền mặt tháng này" |
| | 3 | không có lô / hạn dùng | "những sp nào đang còn hàng có hạn dùng từ 20/05/2026 đến hết 18/08/2026" |
| | 2 | không có lý do hủy / trả | "thang 3/2026 co bnhiu don bi huy vi giao tre" |
| | 1 | không có nhóm khách | "doanh thu từ khách nhóm thân thiết chiếm bao nhiêu phần trăm" |
| **C. Ngoài phạm vi dữ liệu** | 7 | đánh giá chủ quan (6), kiến thức bên ngoài (1) | "Ai là người lành nghề nhất trong số nhân viên?"; "thuốc có hoạt chất nhôm phosphat người lớn nên uống mỗi lần mấy viên" |

## Nhận xét
- Hầu hết câu unanswerable **quyết định được bằng code**, không cần LLM đoán:
  - **A**: so khoảng ngày của bảng cần dùng với kỳ hỏi và kỳ so. Kỳ so nằm ngoài dữ liệu cũng làm câu thành unanswerable.
  - **B**: trường hoặc bảng mà loại câu cần không có trong bảng chuẩn của cửa hàng.
  - **C**: LLM đánh dấu `out_of_scope` khi hiểu câu hỏi.
- **Rủi ro lớn nhất ở nhóm B**: "không có" có thể là do **mapping bỏ sót cột**, chứ không phải shop thật sự không ghi. Chỉ trả unanswerable khi mapping qua kiểm tra, profiling không thấy cột nào giống, và README cũng không nhắc tới. Còn nghi ngờ thì bỏ trống.
- Nhóm A cần luật §7: kỳ **chỉ một phần** nằm ngoài dữ liệu thì tính trên phần có dữ liệu, không phải unanswerable.

## Hệ quả cho hợp đồng
- `Signals` cần: `period_coverage` (`full` / `partial` / `none`, cho cả kỳ hỏi và kỳ so), `required_fields_present`, `mapping_ok`, `out_of_scope`.
- Mỗi hàm tính khai báo các trường bảng chuẩn mà nó cần (`requires`), để biết câu nào rơi vào nhóm B.
- Bảng chuẩn lưu khoảng ngày có dữ liệu của từng bảng.
