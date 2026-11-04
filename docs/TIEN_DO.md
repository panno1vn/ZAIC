# Tiến độ và bối cảnh dự án (bàn giao giữa các phiên làm việc)

*Cập nhật cuối: phiên 4 với Claude. **Phiên mới đọc [BAN_GIAO_PHIEN_4.md](BAN_GIAO_PHIEN_4.md) trước**, rồi tới file này, mục 9–10 của [KE_HOACH_DataMate.md](KE_HOACH_DataMate.md) và [HAN_CHE_VA_CAI_THIEN.md](HAN_CHE_VA_CAI_THIEN.md).*

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
- **Ngày 04/11:**
  - **K3:** phần không cần GPU đã xong:
    - client `llama-server` có timeout;
    - prompt + kho 123 ví dụ BM25;
    - `parse_question` đối chiếu với baseline;
    - lệnh chấm `python -m datamate.eval.k3`.

    Phần chạy model thật **chưa làm được**: mạng 4G, và máy chặn chạy `.exe` tải về (H20). File model đã tải dở 507 MB ở `E:\llm\models\Qwen3-8B-Q4_K_M.gguf.part`; có wifi thì tải tiếp bằng `curl -C -`.
  - **G2 phần 1:** đủ 8 biến đổi, `sources` dạng glob, điền xuống theo §8 trước bước bỏ dòng trùng, ngày đơn = dòng sớm nhất, `base_qty` tự suy từ bảng quy đổi.
  - **Mapping tay 4 cửa hàng:** biz_101, biz_103, biz_105, biz_117. Cả 4 qua đủ 6 bước kiểm tra; `oracle --all` ra **51 đúng / 0 sai / 345 bỏ trống**.
  - Sửa R23 (dòng chú thích, dòng "Tổng tháng") và R24. Tổng cộng 200 test.
- **Ngày 05/11 (có wifi):**
  - Model Qwen3-8B Q4_K_M đã tải xong ở `E:/llm/models/` (5.027.783.488 byte, sha256 khớp bản chính chủ). llama.cpp chờ leader tự tải, vì máy chặn mình chạy `.exe` tải về.
  - **Mapping tay đủ 8 cửa hàng**, chọn theo độ phủ: thêm biz_120, biz_123, biz_124, biz_126. `oracle --all` ra **113 đúng / 0 sai / 677 bỏ trống** trên 790 câu.
  - **H17 xong:** thêm 4 bước kiểm tra theo nghĩa (nay 10 bước), ngưỡng đo trên 8 mapping. Phá có chủ đích 8 kiểu thì bị chặn cả 8.
  - Sửa **R25**: `41,785tr` bị đọc gấp 1000 lần.
  - **G4 bộ tính ngày xong** (trừ `anchor_price`): tính được kỳ cho 122/123 plan viết tay.
  - Loader chuẩn hoá Unicode NFC. Tổng cộng 239 test.
  - **K3 xong** (sau khi leader chạy llama-server ở cổng 8091), qua 3 lần chạy:
    - Lần 1: plan khớp 69,9%.
    - Lần 2: thêm schema sinh output tách theo loại câu, lên 83,7%; 0 câu bỏ sót bộ lọc.
    - Lần 3: thêm kiểm tra bộ lọc có căn cứ.

    1,8 giây/câu; chạy lại 2 lần cho plan giống hệt. Đã vượt mốc dừng 70%. Tổng cộng 247 test.
- **Phiên 3 (ngày thật 03/11; theo kế hoạch là T1 sáng 06/11): T1 gom cụm mẫu câu, xong.** Chi tiết ở [research/templates.md](research/templates.md).
  - `datamate/nlu/templates.py`:
    - `template_text`: bỏ dấu, **gỡ lỗi gõ telex** khi tắt bộ gõ, che số và tên, bỏ từ đệm;
    - `NameIndex`;
    - `plan_shape`.

    Viết ở đây để T4 dùng lại.
  - `tools/research/templates.py` sinh ra `assets/plans/templates_train.json` và bảng trong tài liệu. Chạy lại cho kết quả giống hệt.
  - Kết quả:
    - **450 cụm, 95,3% câu nằm trong cụm ≥ 2 câu** (đạt tiêu chí ≥ 95%);
    - 94,1% câu nằm trong cụm có mặt ở ≥ 2 cửa hàng;
    - **30,3% câu train nằm trong cụm đã có hàm** (cận trên);
    - T3: 55,2%; v2: 13,2%.
  - **Đổi so với kế hoạch: `token_sort_ratio` thay `token_set_ratio`.** `token_set_ratio` cho 100 điểm khi câu này chứa trọn câu kia, nên ở ngưỡng 90 có 44 cụm lẫn plan, so với 6 khi dùng `token_sort_ratio`.
  - Thêm bước tách cụm theo kiểu đáp án train, vì "5 khách…" (list) khác "khách nào…" (string).
  - LLM (Qwen3-8B) đọc 576 câu đại diện. Đã sửa các mẫu nó đọc sai bằng **26 plan tay mới** ([assets/plans/t1_reps.jsonl](../assets/plans/t1_reps.jsonl)). Kho ví dụ tăng từ 123 lên 149 plan.
    - Lỗi lớn nhất: "giá nhập bình quân" bị đọc thành `avg_order_value`, làm 63 câu v2 bị tính sang T3.
    - "Tính riêng hôm nay" thì bị bịa bộ lọc; cổng kiểm tra bộ lọc có căn cứ đã chặn được.
  - Ghi N5–N8 vào file hạn chế. **N7: baseline đọc 0/290 câu có lỗi gõ telex; gỡ telex thì đọc được 35.** Sửa ở T3, kèm chạy lại K3.
  - 255 test qua (thêm 8 ở `tests/test_templates.py`).
- **Phiên 3: T2 G6 nối tên, xong.** Chi tiết ở [research/linking.md](research/linking.md).
  - `datamate/nlu/linking.py` có 3 bước: khớp tuyệt đối → tên đầy đủ có trong câu hỏi → so khớp mờ `token_sort_ratio` ≥ 90, cách ứng viên thứ hai ≥ 5 điểm.
  - Tên hàng nối về mã hàng; kênh bán và thanh toán nối về mã qua `assets/linking/synonyms.json` (chỉ có từ thấy trong train), lọc bằng `linking.matches`.
  - `link_entities` nhận thêm câu hỏi; pipeline đã truyền vào.
  - Lệnh đo `python -m datamate.eval.linking`. Trên 220 câu có bộ lọc của 8 cửa hàng (231 giá trị): tên hàng nối 100%, khách 94%. **Mọi giá trị không nối được đều thuộc câu `unanswerable`.**
  - Sửa R26: bỏ đơn vị đếm ở đầu tên hàng; tên LLM chép sai thì nối theo tên trong câu hỏi.
  - `oracle --all` vẫn 113 đúng / 0 sai. 267 test qua.
- **Phiên 3: T3 G5 nhóm bán hàng + nối LLM, xong.** `oracle --all --llm-url` trên 790 câu của 8 cửa hàng: **567 đúng / 0 sai / 223 bỏ trống, PA +0,718** (trước T3: 113 đúng, PA +0,143). Lượt đầu sai 2 câu do LLM đọc sai ý câu; đã sửa R30 bằng cổng `ungrounded_measures`.
  - `datamate/metrics/frames.py` (bảng dùng chung, bộ lọc dùng chung).
  - `datamate/metrics/sales.py` viết lại: 7 chỉ số; value / compare / share / rank / count_where / trend / series / hàng ế.
  - `python -m datamate.eval.check_plans`: chạy plan có sẵn qua cả chuỗi rồi chấm. Kết quả **230 đúng / 2 sai / 131 bỏ trống** trên 363 câu của 8 cửa hàng; 2 câu sai là LLM đọc sai ý câu (N12, cần cổng T4).
  - Đã sửa:
    - R27: "kl" bị coi là khách; sửa bằng `blank_walk_ins`.
    - R28: `count_where` không có measure không tìm được hàm.
    - R29: LLM bịa ngày; thêm cổng: ngày / năm của plan phải có căn cứ trong câu.
  - `predict` và `oracle` có `--llm-url`; `oracle` có thêm `--llm-cache` (chỉ dùng khi phát triển).
  - Mapping không đạt thì pipeline không gọi LLM.
  - 282 test qua.
- **Phiên 3: N7 + T4 (đang chạy).**
  - N7: `baseline.fold` gỡ lỗi gõ telex. Khi LLM không cho plan dùng được thì dùng plan của baseline. `oracle --all --llm-url`: **571 đúng / 0 sai / 219 bỏ trống, PA +0,723**.
  - T4, code đã có:
    - `eval/build_bank.py`: LLM đọc 3000 câu với ví dụ của cửa hàng khác, kiểm chứng plan bằng đáp án hoặc theo mẫu, ghi `assets/plans/verified_train.jsonl`;
    - `nlu/twins.py` + `pipeline.twin_check`: cổng câu anh em, `Signals.twin_ok`;
    - `eval/twin_gate.py`: chọn ngưỡng theo kiểu bỏ ra một cửa hàng.
- **Đêm 03→04/11: T4 xong.** Mọi số dưới đây đo trung thực: LLM không thấy ví dụ của chính cửa hàng đang chấm.
  - `build_bank`: 3000 câu, khoảng 1,4 giờ. Kho có **2117 plan đã kiểm chứng**: 565 bằng đáp án, 1552 theo mẫu.
  - Lượt `oracle` trung thực đầu tiên (790 câu, tắt cổng): **575 đúng / 7 sai**; cả 7 câu là LLM đọc sai ý. Cổng câu anh em chặn được 6/7 nhưng mất 11 câu đúng.
  - Đã sửa R31–R33, N14, N15 ([HAN_CHE mục I](HAN_CHE_VA_CAI_THIEN.md)): cổng phải có câu anh em thật; luật căn cứ cho câu hỏi tồn / đơn giá / nhập hàng; ca cần chữ "sáng" / "chiều"; bỏ bộ lọc huỷ thừa; gộp loại kỳ theo họ.
  - **Sau khi sửa: tắt cổng 575 đúng / 0 sai (PA +0,728); bật cổng 570 đúng / 0 sai (PA +0,722).** Ngưỡng 0 (chỉ đòi câu anh em cùng dạng) đã ghi trong `configs/default.json`. Giữ cổng hay không: xem N16.
  - K3 trên 149 câu (sau N7 và các cổng mới): **khớp hoàn toàn 76,5%**, 1,8 giây/câu. 15 plan rỗng: 12 bị cổng loại vì LLM bịa bộ lọc / ngày hoặc đọc sai chỉ số, 3 có JSON sai khuôn; không plan nào bị loại oan.
  - 287 test qua.
- **Sáng 04/11: chỉ số v2** ([HAN_CHE mục J](HAN_CHE_VA_CAI_THIEN.md), [metrics/README](../datamate/metrics/README.md)). Mỗi công thức đều được dò với đáp án train trước khi viết.
  - `metrics/stock.py` (§5): tiền nhập, giá nhập bình quân, giá bán ngày D, tồn đến hết ngày X (cả `[chẵn, lẻ]`), xếp nhà cung cấp.
  - `metrics/debt.py` (§4): nợ thêm, trả nợ, còn nợ, số khách nợ, xếp khách nợ (bảng).
  - `metrics/industry.py` (§6): số đợt giao.
  - `sales.py`: lãi gộp, hàng lời nhất, lãi ròng.
  - Cổng căn cứ mới (R34–R36): tồn cần chữ về tồn; tiền nhập cần "tiền / giá trị" (phòng dòng "nhà cung cấp chính" của rulebook public); lãi gộp không dùng khi câu nói "ròng".
  - `check_plans`: **316 đúng / 0 sai / 47 bỏ trống** trên 363 câu (trước: 230 / 2 / 131).
  - Plan LLM của `build_bank` ở 8 cửa hàng có mapping: **690 đúng / 0 sai** / 58 bỏ trống (trước: 565 / 0 / 184). Kho đã kiểm chứng: 2390 plan.
  - `oracle` có LLM sau v2, đo trung thực trên 8 cửa hàng có mapping tay: bật cổng **699 đúng / 0 sai**, tắt cổng 709 đúng / 0 sai.
- **Trưa 04/11: T5 mapping tự động** ([HAN_CHE mục K](HAN_CHE_VA_CAI_THIEN.md), [mapping/README](../datamate/mapping/README.md)).
  - `mapping/transfer.py`: chuyển mapping tay của cửa hàng cùng họ định dạng sang cửa hàng mới.
    - Theo tên cột: định dạng xuất từ phần mềm.
    - Theo nghĩa: LLM chọn cột, có mẫu giá trị và mô tả cột trong README; dùng cho sổ tay đổi tên cột.
    - Vẫn phải qua 10 bước kiểm tra.
  - Mapping tay thêm: biz_115 (họ `So_chi_tiet_ban_hang`), biz_111 (họ csv `don_hang / chi_tiet_don`).
  - Sửa ở bước dựng dữ liệu chuẩn (áp cho mọi mapping):
    - gộp các cách viết của một tên;
    - "Phí phục vụ" không phải mặt hàng;
    - bỏ dòng tổng giữa sheet và dòng header lặp lại;
    - cho phép ≤ 0,5% đơn không rõ trạng thái.
  - Cổng căn cứ mới: năm của ngày, "quý" ≠ tháng, bộ lọc thứ cần tên ngày, "bao nhiu", "bán được bao nhiêu ly".
  - **`eval.mapping` (30 cửa hàng train, mapping của chính cửa hàng bị bỏ khỏi ví dụ, plan LLM đã lưu): 1881 đúng / 0 sai / 1119 bỏ trống, PA +0,627** (sau khi ghép bảng theo README + chốt R43).
  - Cả chuỗi với LLM (`oracle --all --auto-mapping`): v1 830 đúng / 0 sai; v2 1060 / 0; v3 1570 / 0; **v4 1712 / 0 (PA +0,571); v5 1815 / 0 / 1185 bỏ trống (PA +0,605)**.
  - Public: 8/14 cửa hàng có mapping qua kiểm tra (trước T5: 0).
  - **Review cuối phiên 04/11** (HAN_CHE mục L): sửa R44 (mô tả README lấy nhầm bảng), R45 (ngày ảnh tồn chỉ khi README ghi rõ).
  - **N23, mapping dựng từ mô tả cột trong README** (không cần LLM): `eval.mapping` cả hệ **2294 đúng / 0 sai / 706 bỏ trống, PA +0,765**; riêng đường README 2048 / 0 trên 25/30 cửa hàng. Public không đổi (8/14).
  - **Public lượt 1** (04/11 18:22, trước N23): `outputs/public_run1/submission.jsonl`, 370 trả lời / 630 bỏ trống, 23 phút. **Điểm public 0,316 → 343 đúng / 27 sai (7,3% số câu trả lời).** Train báo 0 sai: tỉ lệ sai thật trên cửa hàng mới là 7% (N24).
    - Bỏ trống: 360 vì 6 cửa hàng chưa map; 128 hàm không ra kết quả; 109 không đọc được câu; 28 cổng câu anh em; 5 ngoài phạm vi.
    - Không phải do thuật ngữ mới của rulebook public (các câu có thuật ngữ mới đều đã bỏ trống), cũng không phải do mapping ở 3 cửa hàng map được bằng hai đường (140/140 câu giống nhau).
  - 329 test qua.
- **Phiên 4 (tối 04/11 ngày hệ thống; HAN_CHE mục M):**
  - **N25, cổng hoà hạng:** bộ sinh đề bỏ các câu hoà (train 0/281 câu xếp hạng hoà, trong khi xếp khách theo số đơn của một tháng hoà ở hạng 1 tới 39%). Bảng xếp hạng của hệ mà hoà thì bỏ trống. Train không mất câu nào; public lượt 1 chạy lại thì chặn 3 câu `sales.rank`.
  - **N26, cửa hàng chỉ có bảng đơn** (cột chuẩn `orders.goods_amount` = tiền hàng của đơn = doanh thu §1): biz_110 từ 0 lên **37 đúng / 0 sai**. Thêm kiểm tra nghĩa "tiền hàng của đơn khớp tổng dòng" (train 4/4 cửa hàng khớp 100%).
  - **`tools/replay_run.py`:** chạy lại một lượt từ log (mapping, plan) bằng code hiện tại, không cần LLM, chỉ in số đếm. Khớp 1000/1000 dòng với lượt 1 và với file `tat_cong_cau_anh_em.jsonl` (chỉ khác ở các câu cổng hoà hạng chặn).
  - **N28, bật unanswerable nhóm A** (kỳ hỏi nằm hoàn toàn ngoài khoảng ngày có dữ liệu, §7): đo trước trên train 16/16 câu đúng.
  - **`eval.mapping --llm-url`: 2347 đúng / 0 sai / 653 bỏ trống, PA +0,782** (sau N25 + N26: 2331 / 0, +0,777). 337 test qua.
  - **N29, bổ sung thuộc tính theo README** cho mọi mapping ứng viên (nhóm khách, nhân viên, thanh toán, kênh, nhóm hàng, hoạt chất, kê đơn; thêm cả danh mục hàng nếu mapping chưa có): phần 1 cho **2407 / 0 / 593, PA +0,802**.
  - **N30, plan đọc đúng mà bị cổng căn cứ bỏ:** bỏ bộ lọc "đơn hoàn thành" chỉ nhắc lại mặc định §1; nhận "tm", "tiền tươi", "ck" theo bộ từ đồng nghĩa của bước nối tên. Train thêm 28 câu có plan.
  - **`eval.mapping --llm-url` cuối phiên 4: 2433 đúng / 0 sai / 567 bỏ trống, PA +0,811.** 344 test qua.
- **Tài liệu khác:** sổ tay nhóm (artifact, riêng tư) https://claude.ai/artifact/SkCWcHheFw2NE6obQzUPxT; [KE_HOACH_DataMate.md](KE_HOACH_DataMate.md); [data_cards/README.md](data_cards/README.md) (chia 30 cửa hàng train cho thành viên A–D); [rules_notes.md](rules_notes.md).

## 4. Trạng thái hiện tại
- 255 test qua (`python -m pytest`; thêm `-m slow` để chạy cả split public thật). T1 xong; việc tiếp theo là T2 (G6 nối tên), rồi T3 theo danh sách ở [research/templates.md](research/templates.md).
- Chạy bình thường: mọi câu bỏ trống, vì `map_business` (G2) chưa có. Chạy với mapping tay: biz_101 PA +0,70.
- **Git:** đã commit ngày 1 (`449deaf`) và ngày 2–4 (`cc6908c`). File này và các bản sửa của review lần 2 chưa commit; leader tự commit.

## 5. Việc tiếp theo
**Từ 02/11 leader làm một mình, 14 giờ/ngày: lịch mới ở [KE_HOACH_DataMate.md mục 9](KE_HOACH_DataMate.md). Các mục bên dưới về chia vai không còn áp dụng; 03/11 (G1) và 04/11 (G2 phần 1; K3 chỉ xong phần không cần GPU) đã xong. 05/11 (8 mapping tay, H17, G4) đã xong. K3 cũng đã xong (83,7%). Ngày tiếp theo là T6 06/11: G6 nối tên, G5 thư viện hàm nhóm bán hàng.**

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
- (04/11, N22) Có được xem cấu trúc file và README của public test để viết luật đọc dữ liệu dùng chung không. Câu hỏi ở BAN_GIAO_PHIEN_3 mục "Việc tiếp theo".

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
