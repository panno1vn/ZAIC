# Các loại bảng và thông tin trong dữ liệu 44 cửa hàng

Dò theo tên file, tên sheet và tên cột (`tools/research/inventory_entities.py`). Kết quả là ước lượng: tên cột ngắn như "xe", "bảo hành" có thể khớp nhầm. Bước này chỉ xem cấu trúc file của cửa hàng public test, không gắn nhãn hay tự trả lời câu hỏi nào.

## Hình dạng file
- Train: 7 cửa hàng chỉ có csv, 21 chỉ có xlsx, 1 sqlite (17 bảng), 1 xlsx + csv. Public: 3 csv, 9 xlsx, 1 sqlite, 1 xlsx + csv.
- 1 đến 23 file mỗi cửa hàng. 20 cửa hàng có file Excel nhiều sheet (thường là mỗi tháng một sheet).
- Header gộp 2 dòng phát hiện được ở biz_105, biz_117, dev_004, dev_013; có thể còn nhiều hơn.

## Thông tin có trong bao nhiêu cửa hàng

| Thông tin | Train /30 | Public /14 | Bảng chuẩn |
|---|---:|---:|---|
| ngày / giờ | 30 | 14 | `orders.order_time` |
| mặt hàng | 30 | 13 | `lines.product_name` |
| trạng thái đơn | 28 | 11 | `orders.status` |
| đơn vị, quy đổi | 28 | 8–10 | `lines.unit`, `unit_conversions` |
| số lượng | 27 | 12 | `lines.qty` |
| thành tiền | 26 | 11 | `lines.line_amount` |
| mã đơn | 25 | 12 | `orders.order_id` (không có thì mỗi dòng là một lần ghi) |
| tên khách | 24 | 13 | `orders.customer_name` |
| ghi chú | 21 | 12 | `orders.note` (có shop ghi trạng thái ở đây) |
| tồn kho | 20 | 7 | `inventory` |
| đơn giá | 19 | 6 | `lines.unit_price` |
| mã hàng, nhóm hàng | 18 | 7–8 | `products` |
| đã trả / còn nợ | 15 | 6 | `payments` |
| nhập hàng | 12 | 7 | `purchases` |
| mã khách, nhóm khách | 8–10 | 3–5 | `orders.customer_key`, `customers` |
| kênh bán, hình thức thanh toán | 9–10 | 4–5 | `orders.channel`, `orders.payment_method` |
| giảm giá, VAT, giá vốn | 6–8 | 2–4 | `orders.order_discount`, `orders.vat`, `lines.unit_cost` |
| lô, hạn dùng; hoạt chất, kê đơn | 4–6 | 1–2 | `lots`, `products` |
| lịch sử giá | 4 | 2 | `price_history` |
| nhân viên / thợ | 4 | 5 | `orders.employee`, `employees` |
| giao nhiều đợt; báo cáo ca | 3–5 | 1–2 | `deliveries`, `shift_reports` |
| chi phí | 1 | 1 | `expenses` |
| **trả góp, thu máy cũ / IMEI, sheet ghi tắt** | **0** | **1–2** | chưa có trong train → `extra_tables` |

## Kết luận cho schema chuẩn
1. **Lõi** có ở hầu hết cửa hàng: `orders` + `lines` (ngày, trạng thái, mặt hàng, số lượng, đơn vị, thành tiền). Hàm doanh thu và đếm chỉ cần lõi này.
2. **Phụ** có ở một phần cửa hàng: `products`, `unit_conversions`, `customers`, `payments`, `returns`, `purchases`, `inventory`, `price_history`, `lots`, `expenses`, `deliveries`, `shift_reports`, `employees`. Thiếu bảng nào thì câu hỏi cần bảng đó **có thể** là unanswerable (xem [unanswerable.md](unanswerable.md)).
3. **Thông tin lạ**: public đã có trả góp, thu máy cũ, sổ sửa xe chưa từng có trong train; private chắc chắn có thêm. Schema cần chỗ chứa `extra_tables` (giữ nguyên cột, kèm mô tả) để đường sinh code [D2] dùng được.
4. Sổ không có mã đơn (sổ ghi tay mỗi dòng một mặt hàng): mỗi dòng là một lần ghi (§8). Mapping phải ghi rõ trường hợp này.
5. Mọi bảng phải ghi lại **khoảng ngày có dữ liệu**, để [E] kiểm tra kỳ hỏi có nằm trong dữ liệu không.
