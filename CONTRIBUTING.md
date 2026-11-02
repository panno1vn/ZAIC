# Quy trình làm việc

## Git
- Nhánh chính là `main`. Không push thẳng lên `main`.
- Mỗi việc một nhánh, đặt tên `ten-nguoi/viec-ngan`, ví dụ `lan/parse-money`.
- Xong việc thì mở pull request vào `main`; leader review rồi mới merge.
- Commit nhỏ, message nói rõ đã làm gì: `loader: parse tiền dạng 25k, 30.500đ`.

## Trước khi mở pull request
- [ ] `python -m pytest` qua hết.
- [ ] Nếu sửa code ảnh hưởng tới đáp án: chạy `python -m datamate.eval.run` trên train, ghi PA trước và sau vào mô tả pull request.
- [ ] Hàm mới có test; hàm public có type hint và docstring một dòng.
- [ ] Không đổi hợp đồng (`datamate/contracts/`, có từ T3 03/11) nếu chưa được leader đồng ý.

## Luật thi phải giữ trong code (vi phạm có thể bị loại)
- [ ] **Không commit dữ liệu** của BTC (`data/`, file zip, file trích từ dữ liệu). Repo phải để private.
- [ ] **Không có logic theo id**: không viết `if business_id == ...` hay tra cứu theo id câu hỏi. Test `tests/test_no_id_logic.py` sẽ chặn. `business_id` chỉ dùng để tìm thư mục dữ liệu.
- [ ] **Không dùng dữ liệu public/private test** để tạo ví dụ mẫu, từ điển, ngưỡng hay mapping. Chỉ dùng cửa hàng train hoặc dữ liệu nhóm tự tổng hợp.
- [ ] **Không gọi mạng lúc chạy**: không API, không tải model hay dữ liệu khi inference.
- [ ] **Thư viện và model phải có giấy phép mã nguồn mở OSI** (Apache-2.0, MIT, BSD…).
- [ ] Code chạy lúc inference không ghi vào `/data` (chỉ đọc); file tạm ghi vào `/tmp` hoặc `outputs/`.

## Nhịp làm việc
- Hằng ngày nhắn 3 dòng vào nhóm: hôm qua làm gì, hôm nay làm gì, đang vướng gì.
- Thứ Hai lập kế hoạch tuần (30 phút). Thứ Ba và thứ Năm phân tích lỗi (45 phút).
