# Bàn giao phiên 3 → phiên 4

*Phiên 3 với Claude, ngày hệ thống 03/11/2026. Lịch thật vẫn đi trước kế hoạch: T1–T3 theo kế hoạch là 06–07/11.*

## Bắt đầu phiên mới thế nào
Dán vào phiên chat mới:

> Đọc `docs/BAN_GIAO_PHIEN_3.md`, rồi `docs/TIEN_DO.md` và mục 9–10 của `docs/KE_HOACH_DataMate.md`. Kiểm `git status` và `python -m pytest`. Sau đó làm việc tiếp theo ở mục "Việc tiếp theo" của file bàn giao.

Việc cần LLM thì mở llama-server như phiên 2 (cổng 8091):
```powershell
cd E:\llm\llama-b12064
.\llama-server.exe -m E:\llm\models\Qwen3-8B-Q4_K_M.gguf --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port 8091
```
Tốc độ đo trong phiên 3 khoảng **4 giây/câu**, chậm hơn 1,8 giây lúc K3; chưa rõ vì sao.

## Phiên 3 đã làm gì
1. **T1, gom cụm mẫu câu.** Chi tiết ở [research/templates.md](research/templates.md).
   - 450 cụm; 95,3% câu nằm trong cụm ≥ 2 câu; 30,3% câu train nằm trong cụm đã có hàm (đo trước T3).
   - Code: `datamate/nlu/templates.py` (`template_text` có gỡ lỗi gõ telex, `NameIndex`, `plan_shape`), `tools/research/templates.py`, `assets/plans/templates_train.json`.
   - Viết tay **26 plan mới** cho các cụm LLM đọc sai: `assets/plans/t1_reps.jsonl`. Kho ví dụ BM25 tăng từ 123 lên 149, nên số K3 cũ (83,7% trên 123 câu) không còn so thẳng được.
2. **T2, G6 nối tên.** Chi tiết ở [research/linking.md](research/linking.md).
   - `datamate/nlu/linking.py` có 3 bước: khớp tuyệt đối → tên đầy đủ có trong câu hỏi → so khớp mờ. Tên hàng nối về mã hàng; kênh bán và thanh toán nối về mã qua `assets/linking/synonyms.json`.
   - Trên 220 câu có bộ lọc: tên hàng nối 100%; mọi tên không nối được đều thuộc câu `unanswerable`.
3. **T3, G5 nhóm bán hàng.** `datamate/metrics/frames.py`, `datamate/metrics/sales.py` viết lại.
   - `python -m datamate.eval.check_plans` (plan có sẵn → cả chuỗi → chấm): 230 đúng / 2 sai / 131 bỏ trống trên 363 câu.
   - Nối LLM: `predict` / `oracle` có `--llm-url`; `oracle` có `--llm-cache outputs/llm_cache.jsonl` để chạy lại không tốn LLM.
   - Đã sửa các lỗi tìm được: R26 (nối tên), R27 ("kl" là khách lẻ), R28 (`count_where` không measure), R29 (LLM bịa ngày → cổng ngày / năm có căn cứ).
   - Kết quả `oracle --all --llm-url` trên 790 câu: xem mục "Trạng thái" bên dưới.
4. **T4, kho đã kiểm chứng + cổng câu anh em**, chạy qua đêm 03→04/11: xem mục "Đêm 03→04/11".

## Quyết định và phát hiện cần nhớ
- **Plan LLM sai ý câu là nguồn −1 còn lại** (N12): "số ddown" bị đọc thành doanh thu, "dthu thuốc kê đơn" bị đọc thành tỉ trọng. Hàm tính không sai. Cách chặn đúng là cổng "câu anh em" (T4).
- **Cổng căn cứ** (`nlu.accept_plan`): bộ lọc, ngày và năm của plan LLM phải có trong câu. Năm không có trong câu thì bỏ, để §2 tự suy.
- `blank_walk_ins` ở bước dựng dữ liệu chuẩn: "khách lẻ / lẻ / kl / vãng lai" và ô rỗng đều là không có mã khách.
- Trend chỉ hỏi chiều tăng (cả 21 câu train); hợp đồng chưa ghi được chiều giảm (N11).
- `baseline.fold` chưa gỡ telex (N7). Sửa thì ví dụ BM25 đổi, phải chạy lại K3.

## Trạng thái (sáng 04/11)
- **Git:** commit cuối là `249827f`. Toàn bộ việc của phiên 3 **chưa commit**. Lệnh cho leader ở cuối file.
- **Test:** 315 qua.
- **`oracle --all` không LLM:** 116 đúng / 0 sai.
- **`oracle --all --llm-url`, đo trung thực** (790 câu, 8 cửa hàng, LLM không thấy ví dụ của chính cửa hàng, cache ở `outputs/llm_cache.jsonl`):
  - bật cổng câu anh em: **570 đúng / 0 sai / 220 bỏ trống, PA +0,722**;
  - tắt cổng: 575 đúng / 0 sai / 215 bỏ trống, PA +0,728.
- **K3** (149 câu): khớp hoàn toàn 76,5%, 1,8 giây/câu.
- Số 571 đúng / 0 sai trước đó **lạc quan**, vì kho BM25 chứa chính câu đang chấm. `oracle` giờ mặc định loại ví dụ của chính cửa hàng; muốn chạy như cũ thì thêm `--see-own-examples`.

## Đêm 03→04/11 đã chạy gì (T4)
Nhật ký: `outputs/overnight.log`.
1. **`build_bank`** (23:40 → 01:10): LLM đọc 3000 câu với ví dụ của cửa hàng khác. Kho `assets/plans/verified_train.jsonl` có 2117 plan.
2. **`twin_gate`:** trên 8 cửa hàng có mapping, không ngưỡng nào có câu sai, nên bảng không chọn được ngưỡng. Thêm phép đo trên 22 cửa hàng không có mapping (plan khác cách đọc đã kiểm chứng của cụm thì nhiều khả năng là đọc sai) và đọc tay 61 câu: điểm giống của câu không tách được câu đúng khỏi câu đọc sai. **Chốt ngưỡng 0**: chỉ đòi có câu đã kiểm chứng cùng dạng plan ở cửa hàng khác.
3. **Lượt `oracle` trung thực đầu tiên**, tắt cổng: 575 đúng / **7 sai**. Cả 7 là LLM đọc sai ý: câu hỏi tồn kho đọc thành số đã bán, "đơn giá" đọc thành doanh thu, "nhập trừ bán", "mấy mặt hàng ế" đọc thành danh sách. Bật cổng: chặn 6/7 câu sai, mất 11 câu đúng.
4. **Đã sửa** (chi tiết ở HAN_CHE mục I), mỗi bản sửa có test:
   - R31: ở ngưỡng 0, plan không có câu anh em nào vẫn lọt cổng;
   - R32: luật căn cứ cho câu hỏi tồn / đơn giá / nhập / "không … món nào";
   - R33: ca sáng / ca chiều cần chữ "sáng" / "chiều" ("Chả cá chiên");
   - N14: bỏ bộ lọc "trạng thái = huỷ" thừa;
   - N15: gộp loại kỳ theo họ khi so dạng.

   Sau đó dựng lại kho, chạy lại hai lượt `oracle` và K3: các số ở mục "Trạng thái".

## Sáng 04/11: chỉ số v2 (xong phần lớn)
- Đã có:
  - nhập hàng, giá bán, tồn kho (`metrics/stock.py`);
  - công nợ (`metrics/debt.py`);
  - số đợt giao (`metrics/industry.py`);
  - lãi gộp / lãi ròng (`sales.py`).
- `check_plans`: 316 đúng / 0 sai / 47 bỏ trống.
- Plan LLM của `build_bank` ở 8 cửa hàng có mapping: 690 đúng / 0 sai / 58 bỏ trống.
- Chi tiết ở HAN_CHE mục J và `datamate/metrics/README.md`.
- `oracle` có LLM, đo trung thực trên 8 cửa hàng có mapping tay: bật cổng **699 đúng / 0 sai**, tắt cổng 709 / 0.

## Trưa 04/11: T5 mapping tự động (xong phần lớn)
- `datamate/mapping/transfer.py` (chi tiết ở `datamate/mapping/README.md` và HAN_CHE mục K): chuyển mapping tay của cửa hàng cùng họ định dạng.
  - Theo tên cột cho định dạng xuất từ phần mềm.
  - Theo nghĩa cho sổ tay đổi tên cột: LLM chọn cột, có mẫu giá trị và mô tả cột trong README.
  - Vẫn qua 10 bước kiểm tra.
- Mapping tay thêm: biz_115, biz_111. Tệp `assets/mappings/signatures.json` (cột, mẫu giá trị, mô tả README của bảng trong các mapping tay) sinh bằng `python tools/mapping_signatures.py`. **Thêm mapping tay mới thì phải chạy lại lệnh này.**
- **Đo** (mapping của chính cửa hàng luôn bị bỏ khỏi ví dụ):
  - `python -m datamate.eval.mapping --llm-url …` (plan LLM đã lưu): **1881 đúng / 0 sai / 1119 bỏ trống trên 3000 câu train**.
  - Cả chuỗi với LLM: `python -m datamate.eval.oracle --all --auto-mapping --llm-url … --llm-cache outputs/llm_cache.jsonl --out …`. v1 830 / 0, v2 1060 / 0, v3 1570 / 0, v4 1712 / 0, **v5 (có ghép bảng theo README) 1815 đúng / 0 sai / 1185 bỏ trống, PA +0,605**.
- Public: 8/14 cửa hàng có mapping qua kiểm tra (trước T5: 0): dev_001, 002, 004, 005, 006, 007, 008, 010.

## Việc tiếp theo
1. ~~Đọc kết quả `oracle` v5~~: 1815 đúng / 0 sai (14:13 ngày 04/11).
2. ~~Review cuối phiên (HAN_CHE mục L)~~: sửa R44, R45; train vẫn 1881 / 0. N22 đã quyết: hỏi BTC, tạm chỉ dùng train.
3. **Tăng độ phủ mapping** (HAN_CHE N20, N23).
   - ~~N23, mapping dựng từ README~~ (xong 04/11): train cả hệ **2294 đúng / 0 sai, PA +0,765**. Public không đổi (8/14).
   - Chỉ dò trên train (trưởng nhóm quyết N22 ngày 04/11), cho tới khi BTC trả lời câu hỏi dưới đây. Còn trượt ở train: biz_110 (chỉ có đơn), biz_123 (sqlite POS), biz_124 (3 nguồn).
   - Câu hỏi gửi BTC (trưởng nhóm gửi):
     > Đội em muốn hỏi về mục 4.2 của thể lệ. Đội không gán nhãn, không xem đáp án, không viết xử lý riêng cho từng cửa hàng hay từng câu hỏi. Đội có được **xem cấu trúc file và README (đầu vào) của public test** để viết các luật đọc dữ liệu dùng chung cho mọi cửa hàng không, ví dụ thêm một cách gọi tên cột vào từ điển chung? Hay đội chỉ được phát triển dựa trên dữ liệu train? Đội cảm ơn BTC.
4. **Đọc N16** (HAN_CHE mục I): giữ hay tắt cổng câu anh em. Mặc định đang bật, ngưỡng 0. Muốn tắt thì đổi `twin_threshold` thành `null`.
5. **Nộp public (N24):** lượt 1 đã chạy 04/11, file `outputs/public_run1/submission.jsonl` (370 trả lời / 630 bỏ trống, đã qua `eval.validate`, chưa có đường README; với public, đường README không đổi gì). Trưởng nhóm nộp lên portal, ghi điểm vào TIEN_DO. Các lượt sau: chạy `predict` (`eval.validate` trước khi nộp). `predict` đã dùng mapping tự động và LLM (`--llm-url`).
6. v2 còn lại (ít câu): tuổi nợ, giá trị tồn, lô / hạn dùng, hiệu ứng tăng giá theo trung bình mỗi ngày.
7. Ghi chú về kho:
   - `verified_train.jsonl` nằm trong `assets/plans`, nên cũng là ví dụ BM25 khi chạy thật. K3, `check_plans` và script T1 chỉ đọc `prompt.HAND_FILES`.
   - Thêm cổng mới thì chạy `python -m datamate.eval.build_bank` (không cần LLM). Lệnh này cho plan đã lưu qua lại các cổng hiện tại rồi dựng lại kho.

## Lệnh hay dùng (thêm so với phiên 2)
| Việc | Lệnh |
|---|---|
| Gom cụm mẫu câu | `python tools/research/templates.py [--llm-url …]` |
| Đo nối tên | `python -m datamate.eval.linking [--llm-url …] --out outputs/linking/run.jsonl` |
| Chấm plan có sẵn | `python -m datamate.eval.check_plans --out outputs/check_plans/run.jsonl` |
| Chạy với LLM + mapping tay (đo trung thực) | `python -m datamate.eval.oracle --all --llm-url http://127.0.0.1:8091 --llm-cache outputs/llm_cache.jsonl --out outputs/oracle_llm` (thêm `--twin-threshold -1` để tắt cổng) |
| Dựng kho đã kiểm chứng | `python -m datamate.eval.build_bank [--llm-url …]` (không có `--llm-url`: chỉ kiểm chứng lại plan đã lưu) |
| Chọn ngưỡng cổng câu anh em | `python -m datamate.eval.twin_gate` |
| Chấm mapping tự động (plan đã lưu) | `python -m datamate.eval.mapping [--llm-url …] [--business …]` |
| Cả chuỗi với mapping tự động | `python -m datamate.eval.oracle --all --auto-mapping --llm-url … --llm-cache outputs/llm_cache.jsonl --out …` |
| Sinh lại danh sách cột của mapping tay | `python tools/mapping_signatures.py` |

## Lệnh commit cho leader
```
git add assets datamate docs tests tools configs
git commit -m "Phiên 3: T1 mẫu câu, T2 nối tên, T3 hàm bán hàng + nối LLM, T4 kho đã kiểm chứng + cổng câu anh em, v2 nhập/giá/tồn/công nợ/lãi/đợt giao, T5 mapping tự động (1881 đúng/0 sai trên 30 cửa hàng); R26-R43"
```
