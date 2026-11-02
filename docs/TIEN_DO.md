# Tiến độ và bối cảnh dự án (bàn giao giữa các phiên làm việc)

*Cập nhật cuối: phiên 2 với Claude (review lần 2, K2, hợp đồng v1.1; 02/11). Phiên mới nên đọc file này trước, rồi tới [KE_HOACH_DataMate.md](KE_HOACH_DataMate.md) và [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md).*

## 1. Bối cảnh
- **Cuộc thi:** Zalo AI Challenge 2026, đề **DataMate**: trả lời câu hỏi tiếng Việt (không dấu, viết tắt) trên dữ liệu kinh doanh của cửa hàng nhỏ (csv / xlsx / sqlite). Nhóm đã bỏ đề LifeMate; dữ liệu LifeMate đã xóa.
- **Đội:** 5 người. Leader là người dùng; 1 thành viên có kinh nghiệm; 3 junior. Vai trò chưa chia; dự kiến chia trong buổi họp sau khi xong xương sống.
- **Mốc:**
  - **Đóng băng T2 16/11/2026 23:59** (nộp Docker qua link Google Drive + checksum, tối đa 2 lần, BTC chỉ chấm lần cuối).
  - Private test phát 9:00 T6 20/11; nộp kết quả trước 23:59 T2 23/11.
  - 02/12 công bố 2 đội đầu; 12/12 kết quả chung cuộc.
- **Chấm điểm:** đúng +1, sai −1, bỏ trống 0. Khớp tuyệt đối. Trả lời một câu unanswerable là sai.
- **Ràng buộc kỹ thuật:**
  - Mọi model cộng lại không quá 15 tỉ tham số; weights công bố trước 01/10/2026; giấy phép OSI.
  - Chạy offline; `/data` chỉ đọc; không có logic theo id cửa hàng hay id câu hỏi; không train trên dữ liệu test, không gắn nhãn tay dữ liệu test.
  - Máy chấm 2× RTX 5090 32GB; tối đa 6 giờ, tính cả lúc load model.
  - Kết quả BTC chạy lại phải lệch không quá 0,03 PA.
  - Được augment và tự tổng hợp dữ liệu từ train.
- **Dữ liệu:** train 3000 câu / 30 cửa hàng; public 1000 câu / 14 cửa hàng. Rulebook train 142 dòng, public 176 dòng (public thêm 3 ngành: mẹ và bé, sửa xe, điện thoại). Bộ private sẽ có ngành mới.

## 2. Quyết định đã chốt
- **Kiến trúc v2:** [architecture/DataMate_kien_truc_v2.png](architecture/DataMate_kien_truc_v2.png) (file sửa được: `.drawio`). Gộp từ bản vẽ của một thành viên, có sửa 3 chỗ chưa hợp lý.
- **Nguyên tắc:**
  - LLM chỉ hiểu câu hỏi và trích xuất; mọi phép tính do code.
  - Không chắc thì bỏ trống.
  - Rulebook là dữ liệu đầu vào: mỗi hàm tính khai báo dòng luật nó dựa vào.
  - Không có logic theo id.
  - Bước nào cũng ghi log.
- **Đường chính:** kế hoạch truy vấn JSON + thư viện hàm [D1]. **Dự phòng:** sinh code [D2], làm nếu kịp.
- **Model đề xuất:** Qwen3-14B (chưa chốt; dự kiến so sánh với Qwen2.5-Coder-14B và Qwen3-8B).
- **Unanswerable chưa bật:** mọi câu bị đánh dấu ngoài phạm vi vẫn bỏ trống cho tới khi đo trên train.
- **Mapping tay chỉ làm cho cửa hàng train.** Công cụ chạy với mapping tay (`datamate/eval/oracle.py`) chỉ dùng để phát triển, không vào Docker.

## 3. Đã làm (kế hoạch ngày 1–4, theo ngày hệ thống đều xong trong 02/11)
- **Ngày 1:**
  - Repo git tại `E:\ZAIC`, nhánh `main`, remote `https://github.com/panno1vn/ZAIC` (phải để private).
  - Môi trường `.venv`; thư mục dữ liệu đổi tên thành `data/`.
  - Scorer §9; lệnh `eval.run` (chia điểm theo kiểu đáp án / ngành / cửa hàng) và `eval.validate`.
  - Bảng cửa hàng train → ngành.
- **Ngày 2:**
  - 4 tài liệu nghiên cứu trong [research/](research/).
  - Hợp đồng v0 (Pydantic) và JSON schema.
  - 24 kế hoạch truy vấn mẫu từ train.
  - Stub cho 12 khối.
- **Ngày 3:**
  - Sửa lỗ hổng hợp đồng H1–H7 (hợp đồng v1, có bảng đối chiếu rulebook → hợp đồng trong [contracts.md](contracts.md)).
  - Pipeline: ghi từng dòng, log mỗi câu, đồng hồ chặn.
  - [R] đọc rulebook (so phiên bản luật, có kiểm tra từ mang nghĩa), [V] thu tín hiệu, [E] 6 cổng; lệnh `predict`.
- **Review:** tìm và sửa 12 lỗi R1–R12 (có test hồi quy), xem mục D trong file hạn chế.
- **Ngày 4:**
  - Bộ khung chạy thật trên biz_101 với mapping tay: **28 đúng, 0 sai, 12 bỏ trống, PA +0,70**.
  - Sửa R13 (luật nhiều phiên bản), R14 (`resolve` nhận `db`, `RawTable.year_hint`).
  - Phiếu việc G1–G7 trong README của từng khối.
- **Review lần 2 (phiên 2, ngày thật 02/11):**
  - Rà lại code ngày 1–4, xác nhận lỗi bằng probe.
  - Sửa R15–R20, có test hồi quy trong `tests/test_review2_fixes.py`:
    - kiểu numpy làm dừng cả lượt chạy;
    - NaN lọt vào file nộp;
    - registry ghi đè im lặng và không chặn bộ lọc chưa hỗ trợ;
    - ô ngày/tiền không đọc được vẫn qua kiểm tra mapping;
    - sqlite NULL thành `"None"`;
    - baseline đọc nhầm câu "cái nào".
  - Ghi các mục còn mở H17–H19, N4 (mục E trong file hạn chế).
  - **Lưu ý về ngày:** các ngày 03/11–05/11 ghi trong tài liệu là ngày **theo kế hoạch**; thực tế cả 4 ngày kế hoạch xong trong 02/11, nên đang đi trước lịch 3 ngày.
- **Chuẩn bị khóa hợp đồng (phiên 2, 02/11):**
  - Kiểm checklist §7 của kế hoạch: đạt hết.
  - **K2:** viết tay plan cho 99 câu train lấy mẫu theo loại câu ([assets/plans/k2_trial.jsonl](../assets/plans/k2_trial.jsonl)); sửa thành **hợp đồng v1.1**, 6 thay đổi, xem [contracts.md](contracts.md):
    - trường lạ là lỗi (R21);
    - mã cho bộ lọc ca / thứ / trạng thái / kê đơn;
    - `list_spec.count`;
    - `count_where` không cần `measures`;
    - khoảng hạn dùng ghi bằng ngày;
    - Tết không ghi năm.
  - Thêm `STOCK_METRICS` cho [C2].
  - Phiếu việc G3, G4, G5 đã cập nhật theo.
- **Kế hoạch làm một mình (02/11):** leader làm toàn bộ, 14 giờ/ngày; lịch theo ngày ở [KE_HOACH_DataMate.md mục 9](KE_HOACH_DataMate.md).
- **Ngày 03/11, G1 loader, xong:**
  - đọc xlsx mọi sheet bằng `python-calamine`, csv (dò dấu phân cách, bảng mã), sqlite;
  - dò header 1–2 dòng, bỏ dòng tiêu đề, bỏ dòng tổng (H18), `year_hint`;
  - kiểu tiền mới (R22), đoán kiểu cột khi profiling;
  - giới hạn 300 giây đọc file mỗi cửa hàng.
  - 44/44 cửa hàng đọc không lỗi. 186 test qua; test chạy cả split public gắn nhãn `slow`. biz_101 vẫn 28 đúng / 0 sai.
- **Tài liệu khác:** sổ tay nhóm (artifact, riêng tư) https://claude.ai/artifact/SkCWcHheFw2NE6obQzUPxT; [KE_HOACH_DataMate.md](KE_HOACH_DataMate.md); [data_cards/README.md](data_cards/README.md) (chia 30 cửa hàng train cho thành viên A–D); [rules_notes.md](rules_notes.md).

## 4. Trạng thái hiện tại
- 186 test qua (`python -m pytest`; thêm `-m slow` để chạy cả split public thật).
- Chạy bình thường: mọi câu bỏ trống, vì `map_business` (G2) chưa có. Chạy với mapping tay: biz_101 PA +0,70.
- **Git:** đã commit ngày 1 (`449deaf`) và ngày 2–4 (`cc6908c`). File này và các bản sửa của review lần 2 chưa commit; leader tự commit.

## 5. Việc tiếp theo
**Từ 02/11 leader làm một mình, 14 giờ/ngày: lịch mới ở [KE_HOACH_DataMate.md mục 9](KE_HOACH_DataMate.md). Các mục bên dưới về chia vai không còn áp dụng; 03/11 (G1 loader) đã xong; ngày tiếp theo là T4 04/11: K3 (LLM) + G2 phần 1 (biến đổi, mapping tay).**

1. **Họp chia vai và khóa hợp đồng.** Gợi ý chia:
   - Senior: G2 + G3.
   - Junior A: G1, sau đó G7.
   - Junior B: G4, sau đó phụ G5.
   - Junior C: G5 + G6.
   - Leader giữ hợp đồng, pipeline, [R] [V] [E], scorer, review.
2. **Leader cần quyết định H13:** kết quả [D2] chỉ được trả lời khi khớp với [D1], hay có cổng riêng.
   - Lưu ý (review lần 2): pipeline chỉ gọi [D2] khi [D1] **không** ra kết quả, nên phương án "khớp [D1]" nghĩa là [D2] không bao giờ trả lời được câu nào, tức là tắt [D2].
   - Đề xuất mới: hoãn [D2] tới sau 09/11. Nếu làm thì dùng cổng riêng, ngưỡng đo trên train.
3. K2 đã xong (hợp đồng v1.1). Còn giao **K3**: thử schema v1.1 với Qwen3-8B trên laptop, đo tỉ lệ JSON hợp lệ và tỉ lệ plan đúng trên 30 câu, dùng 99 plan K2 làm đáp án đối chiếu.
4. Sau khi chia vai, làm theo lịch trong KE_HOACH:
   - 06–09/11: các khối lên bản v1; **09/11 nộp public lần đầu**.
   - 10–12/11: loại câu v2, Docker.
   - 14/11: nộp Docker lần 1.
   - 16/11: đóng băng.
5. Lỗ hổng còn mở: H9–H19, N1–N4, K1–K3. Quan trọng nhất:
   - **H17:** mapping sai nghĩa vẫn qua kiểm tra; nguồn −1 lớn nhất ở bộ private.
   - **H18:** dòng "Cộng" cuối sheet (biz_105). Để sau, đã giao vào phiếu G1, không cần đổi hợp đồng.
   - **N4:** LLM phải ổn định khi BTC chạy lại.
   - **H12:** timeout cho từng câu.
   - **H14:** Docker phải chép `assets/`.

## 6. Câu hỏi chờ BTC trả lời
- Docker guideline: base image, lệnh chạy container, cấu trúc `/data` và `/result`, định dạng nộp image, mốc tính 6 giờ.
- "Data" nộp kèm Docker gồm những gì.
- Dùng API thương mại hoặc trợ lý AI với dữ liệu thi có được không.
- "Không phân biệt dấu câu" khi chấm chuỗi bỏ những ký tự nào.
- Private test có bao nhiêu câu.

Tin nhắn hỏi BTC đã soạn sẵn trong phiên 1 (5 câu về Docker). Phần Docker trong kế hoạch vẫn để trống chờ guideline.

## 7. Môi trường và lệnh hay dùng
- **Máy:** Windows 11, Python 3.10.11, `.venv` (`pip install -r requirements-dev.txt`), GPU RTX 4060 Laptop 8GB.
- **Lệnh:**
  - `python -m datamate.predict --data data/public_test --out outputs/run_public`: chạy agent.
  - `python -m datamate.eval.oracle --business biz_101 --out outputs/oracle_biz101`: chạy với mapping tay rồi chấm luôn.
  - `python -m datamate.eval.run --pred <file> [--business ...]`: chấm file nộp trên train.
  - `python -m datamate.eval.validate --pred <file> --split public_test`: kiểm tra định dạng trước khi nộp.
  - `python -m datamate.rules diff|build data/train/rulebook.md data/public_test/rulebook.md`.
  - `python -m datamate.contracts.export_schema`: chạy sau mỗi lần sửa hợp đồng.
