# Cách nói thời gian trong câu hỏi

Đếm trên 3000 câu train (một câu có thể có nhiều cách nói). Luật mặc định lấy từ rulebook §2.

| Cách nói | Số câu | Ví dụ | Kiểu kỳ trong hợp đồng | Luật |
|---|---:|---|---|---|
| tháng M/YYYY, T7/2026, tháng 8 năm 2025 | ~2185 | "tỉ lệ huỷ đơn tháng 6/2025" | `month` | cả tháng |
| hôm nay, bữa nay, hôm ni, hnay | ~279 | "Tổng doanh thu trong ngày hôm nay" | `today` | chỉ trong ngày |
| ngày D/M/YYYY | ~248 | "Tính đến hết ngày 19/08/2026" | `day` hoặc `until` | xem dòng "đến hết ngày X" |
| hôm qua, bữa qua, hqua | ~172 | "e bua qua cua hang ban duoc may don" | `yesterday` | chỉ trong ngày |
| tháng này | ~152 | "tháng này tổng giá trị các phiếu nhập" | `this_month` | ngày 1 đến hết hôm nay |
| từ X đến Y | ~147 | "từ tháng 2/2026 đến tháng 4/2026" | `range` hoặc `months` | gồm cả X và Y |
| tuần trước, tuần rồi | ~123 | "tuần trước riêng ca chiều bán được…" | `last_week` | trọn tuần T2–CN liền trước |
| N ngày kể từ ngày D | ~82 | "So 7 ngày kể từ ngày 16/03/2025 với 7 ngày ngay trước đó" | `days_from` | N ngày tính cả D, so với N ngày ngay trước D |
| tháng trước, tháng liền trước | ~80 | "so với tháng trước đó, doanh thu tháng 2/2026" | kỳ so `previous` | |
| quý Q/YYYY | ~79 | "tổng doanh thu quý 2/2026" | `quarter` | quý dương lịch |
| ca sáng, ca chiều | ~77 | "doanh thu ca chiều hơn hay kém ca sáng" | **bộ lọc**, không phải kỳ | ca sáng 06:00–13:59, ca chiều 14:00–21:59 theo giờ tạo đơn |
| đến hết ngày X, tính đến | ~75 | "Tính đến hết ngày 25/05/2026, khách còn nợ…" | `until` (tình trạng) | mọi phát sinh **từ đầu dữ liệu** đến hết ngày X |
| so với kỳ trước | ~72 | | kỳ so `previous` | cùng độ dài, liền trước |
| cùng kỳ (năm trước / tháng trước) | ~65 | "so cùng kỳ năm trước, doanh thu tháng 5/2026" | kỳ so `same_period_last_year` / `previous_same_days` | "tháng này so tháng trước" lấy cùng số ngày |
| N ngày gần nhất | ~46 | "dthu 30 ngày gần nhất" | `last_n_days` | N ngày, ngày cuối là hôm nay |
| từ đầu năm | ~32 | "số đơn từ đầu năm tới hết hôm nay" | `ytd` | 01/01 đến hết hôm nay |
| tuần này | ~19 | "3 mặt hàng bán chạy nhất tuần này" | `this_week` | thứ Hai đến hết hôm nay |
| N tháng liền nhau, chuỗi tháng | ~9 | "3 tháng liền nhau kết thúc ở tháng 6/2025… mỗi tháng" | `months` | danh sách tháng |
| Tết | ~5 | "Dịp Tết âm lịch 2026… hơn hay kém 17 ngày trước Tết" | `tet` | 23 tháng Chạp → hết mùng 10 Giêng (tra `calendar.csv`); "trước Tết" = cùng số ngày ngay trước 23 tháng Chạp |
| N ngày tới (hạn dùng) | ~3 | "hết hạn trong 120 ngày tới" | `next_n_days` | từ hôm nay D đến hết D + N |
| tháng/quý không ghi năm | rất ít | "trong tháng 2 nawm 2026…" (thường có năm) | `month` với `year` để trống | năm nay nếu không sau hôm nay, ngược lại năm trước |
| không nêu kỳ | ~18 | "Lô Oresol… gần hết hạn nhất", "khách ở đường…" | không có kỳ | tình trạng tại hôm nay, hoặc câu ngoài phạm vi |

Rulebook public còn có **"trung bình mỗi ngày thứ X của kỳ"** (chia cho số ngày thứ X trong kỳ). Train chưa có câu nào kiểu này, nhưng hợp đồng nên chừa bộ lọc `weekday`.

## Hai loại kỳ khác nhau về bản chất
- **Phát sinh trong kỳ** (`flow`): doanh thu, số đơn, số lượng bán, tiền nhập… Chỉ tính các bản ghi có ngày nằm trong kỳ.
- **Tình trạng đến hết ngày X** (`stock`): còn nợ, còn tồn, chưa giao, số khách còn nợ. Tính mọi phát sinh **từ đầu dữ liệu** đến hết ngày X.

Cùng một ngày X nhưng hai loại cho kết quả khác hẳn nhau. Vì vậy kỳ đã tính xong (`ResolvedPeriod`) phải có trường `mode` để phân biệt.

## Các kiểu kỳ so
`previous` (kỳ liền trước, cùng độ dài) · `previous_same_days` (tháng này so tháng trước, cùng số ngày) · `same_period_last_year` · `before_tet` · `before_days_from` (N ngày trước D, dùng cho hiệu ứng tăng giá).

## Quy tắc chung
- Mọi kỳ tính theo `as_of_date`. Bản ghi sau `as_of_date` coi như chưa xảy ra, riêng trạng thái hủy/trả lấy theo ghi trên đơn.
- LLM chỉ ghi kỳ dạng ký hiệu. Bộ tính ngày [C2] mới đổi ra ngày cụ thể.
