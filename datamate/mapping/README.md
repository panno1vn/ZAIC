# G2 — [B] Mapping về schema chuẩn

**Mục tiêu:** tự động map dữ liệu của **cửa hàng chưa từng thấy** về schema chuẩn. Map sai thì phải bị phát hiện, để cửa hàng đó bỏ trống thay vì trả lời sai.

**Hợp đồng:** `map_business(raw, profile, rulebook, llm) -> Mapping` ([contracts/mapping.py](../contracts/mapping.py)). `build_canonical(raw, mapping) -> CanonicalDB`; `run_checks(db)` chạy 6 bước kiểm tra bắt buộc (`REQUIRED_CHECKS`); `build_card(db) -> DataCard`.

**Đã có (04/11, G2 phần 1):**
- `build_canonical` ([build.py](build.py)):
  - parse theo kiểu, đổi tên cột, `value_maps`, hằng số (hằng số cũng được parse, ví dụ ngày tồn kho `"2026-06-24"` với `parse: date`);
  - **cài đủ 8 biến đổi** của `TRANSFORMS`:
    - `note_contains` nhận thêm `default` ("ghi chú không nhắc trạng thái là đơn hoàn thành");
    - `lookup` nhận `keep_missing`;
    - `order_status_from_lines`: có dòng trả thì đơn là trả hàng; tất cả huỷ thì là huỷ; trộn không rõ thì để trống, tức kiểm tra không qua;
  - `sources` nhận **mẫu glob** (`"SoBanHang.xlsx::*"`);
  - **cột phụ** `_source`, `_row` (mã dòng, cho sổ không có mã đơn), `_year`;
  - **điền xuống theo §8:** ô cấp đơn để trống ở các dòng sau của đơn lấy theo dòng đầu, chỉ trong cùng sheet, làm *trước* bước bỏ dòng trùng;
  - ngày không ghi năm lấy năm của sheet; **ngày của đơn = dòng sớm nhất**, vì dòng trả hàng ghi ngày trả;
  - **`lines.base_qty` tự suy** từ `unit_conversions` khi file không ghi sẵn. Hợp đồng thêm cột `unit_conversions.base_unit`. Đơn vị lạ của một mặt hàng có quy đổi thì để trống, không đoán.
- `run_checks(db, readme)`: **10 bước kiểm tra bắt buộc**.
  - 6 bước cấu trúc (H8, R18).
  - 4 bước theo nghĩa (H17, 05/11): thành tiền khớp số lượng × đơn giá − giảm giá, trạng thái hợp lý, ngày cuối khớp README, số âm chỉ ở đơn trả.
  - Ngưỡng đo trên 8 mapping tay (xem H17 trong file hạn chế). Phá có chủ đích 8 kiểu thì bị chặn cả 8. Xem `detail` của mỗi bước để biết vì sao không đạt.
- **Mapping tay của 4 cửa hàng** ở [assets/mappings/train/](../../assets/mappings/train/): biz_101 (csv phẳng), biz_103 (xlsx theo tháng, dòng nối tiếp để trống, 8 cách ghi trạng thái), biz_105 (sổ ghi tay, header 2 dòng, trả hàng số âm, nhập hàng / tồn / bảng giá), biz_117 (ngày 4 kiểu, giao nhiều đợt, khách lẻ 3 kiểu).
  - Cả 4 qua đủ 6 bước; `oracle --all` ra **51 đúng / 0 sai** / 345 bỏ trống. Phần lớn câu bỏ trống là do [C] mới có baseline.
  - Cách hiểu 'Đang giao dịch' = đang giao (biz_103) có căn cứ: cả 9 đơn đều nằm ở 9 ngày cuối của dữ liệu.
- Công cụ [tools/show_business.py](../../tools/show_business.py) in README và từng bảng (cột, kiểu, mẫu) để viết mapping hay data card. Chỉ dùng cho cửa hàng train.
- `map_business` **chưa có**: chạy bình thường thì mọi cửa hàng vẫn bỏ trống.

**T5, mapping tự động (04/11):** [transfer.py](transfer.py). `map_business` chuyển mapping tay của một cửa hàng train cùng định dạng sang cửa hàng mới.
- **Vì sao chuyển, không dựng từ đầu:** dữ liệu sinh theo vài họ định dạng lặp lại (phần mềm bán hàng, sổ tay, csv POS…). Định dạng xuất từ phần mềm giữ nguyên tên cột; sổ tay thì đổi tên cột theo từng cửa hàng ("Mã phiếu" / "Ma don", "Tiền" / "Amount").
- **Theo tên cột:** mỗi bảng của mapping mẫu nhận các bảng của cửa hàng mới có đủ cột *bắt buộc* nó đọc. Cột tuỳ chọn không có thì bỏ. Hai bảng khác bố cục khớp ngang nhau thì không đoán.
- **Theo nghĩa** (cần LLM):
  - Ghép bảng theo tên file; tên file khác thì theo **mô tả cột trong README** ("mã đơn", "thành tiền sau giảm"…, cần ≥ 50% và hơn bảng thứ hai 10 điểm). Mẫu cùng tên file được thử trước.
  - Với mỗi bảng, LLM chọn cột tương ứng trong các cột thật của cửa hàng mới (enum). LLM được thấy mẫu giá trị và mô tả README của cả hai bên ([assets/mappings/signatures.json](../../assets/mappings/signatures.json), sinh bằng `tools/mapping_signatures.py`).
  - Cột ngày bắt buộc mà LLM bỏ sót thì lấy cột duy nhất còn lại đọc được là ngày.
  - Chốt chặn (R43): hai cột mẫu khác nghĩa không được chung một cột mới; cột mã đơn của dòng hàng phải gom dòng thành đơn.
- **Trạng thái:** từ điển gộp từ mọi mapping tay, sau đó đến từ khoá; chữ có từ khoá của hai trạng thái thì không đọc.
- **Hằng số của cửa hàng mẫu được tính lại:**
  - ngày ảnh tồn = ngày cuối dữ liệu, nhưng chỉ khi README cửa hàng mới ghi "tồn cuối ngày cuối có dữ liệu"; không ghi thì bỏ bảng tồn (R45);
  - `has_time` theo dữ liệu.
- **Sổ không mã đơn:** mẫu kiểu này chỉ dùng cho cửa hàng mà không cột nào gom dòng thành đơn (`_groups_rows`).
- **Dựng dữ liệu chuẩn (mọi mapping):**
  - gộp các cách viết của một tên: hoa / thường, dấu cách đôi, mất dấu (`unify_keys`);
  - dòng "Phí phục vụ" không phải mặt hàng (`mark_fee_lines`);
  - dòng tổng giữa sheet bị bỏ dù nhãn nằm ở cột nào;
  - cho phép ≤ 0,5% đơn không rõ trạng thái; mọi số liệu đơn đó có thể làm thay đổi thì bỏ trống.
- **Đo:** `python -m datamate.eval.mapping [--llm-url …]` (mapping của chính cửa hàng bị bỏ khỏi ví dụ, plan LLM đã lưu, chấm với đáp án train); `python -m datamate.eval.oracle --all --auto-mapping --llm-url …` (cả chuỗi).
- **Mapping tay thêm cho T5:** biz_115 (họ `So_chi_tiet_ban_hang`), biz_111 (họ csv `don_hang / chi_tiet_don`).

**Việc cần làm:**
1. ~~Cài 8 biến đổi~~ (xong 04/11).
2. ~~Điền ô trống của cùng một đơn (§8), dùng `year_hint`~~ (xong 04/11).
3. ~~Mapping tay thêm 4 cửa hàng; H17~~ (xong 05/11).
   - Thêm biz_120 (nhà thuốc xuất từ phần mềm, 10 file nối bằng mã), biz_123 (sqlite POS 17 bảng), biz_124 (3 nguồn, sổ ghi tay dùng tên hàng), biz_126 (nhà hàng, không mã đơn, dòng phí phục vụ).
   - Bốn cửa hàng này được chọn theo độ phủ kiểu dữ liệu: 8 cửa hàng phủ 29/30 kiểu tìm thấy ở 30 cửa hàng train.
   - `oracle --all` trên 8 cửa hàng: **113 đúng / 0 sai / 677 bỏ trống**.
   - Ba cách ghi trạng thái được kiểm bằng dữ liệu: 'Đang xử lý' và 'shipping' là đang giao (chỉ có ở 3 ngày cuối dữ liệu); 'Không giao được' là huỷ (tỉ lệ huỷ khớp đáp án train).
4. `map_business`: luật đồng nghĩa tên cột trước, LLM điền phần còn thiếu (theo [schemas/mapping.schema.json](../contracts/schemas/mapping.schema.json)), chạy kiểm tra, sai thì cho LLM sửa một lần.
5. Nhận diện ngành (§6); bảng quy đổi đơn vị; bảng lạ vào `extra_tables`.

**Thế nào là xong:**
- Với các cửa hàng có mapping tay: chạy bình thường (mapping tự động) ra **cùng điểm** với `python -m datamate.eval.oracle`.
- Không cửa hàng nào qua kiểm tra mà map sai.

**Đọc thêm:** [docs/contracts.md](../../docs/contracts.md), [docs/research/entities.md](../../docs/research/entities.md), rulebook §6, §8.

**Luật thi:** mapping tay chỉ làm cho cửa hàng **train**. Không viết code riêng cho từng cửa hàng.
