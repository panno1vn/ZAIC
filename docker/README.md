# G7 — Docker và vận hành

*(Chi tiết build còn để trống, chờ BTC công bố Docker guideline: base image, lệnh chạy container, cấu trúc `/data` và `/result`, định dạng nộp image.)*

**Đã biết:**
- Image chứa source code, model weights, `predict.sh` và README.
- `predict.sh` đọc `/data`, ghi `/result/submission.jsonl` và `/result/logs/`.
- Container chạy không có mạng, `/data` chỉ đọc; máy chấm có 2× RTX 5090; tối đa 6 giờ.

Lệnh chạy trong container (đã có): `python -m datamate.predict --data /data --out /result`.

**Việc cần làm khi có guideline (từ T3 10/11):**
1. Dockerfile theo base image của BTC; chép **cả** `datamate/`, `configs/`, `assets/` (mục H14: thiếu `assets/` thì mọi câu bỏ trống); weights của model.
2. `predict.sh` với xuống dòng LF (đã ép bằng `.gitattributes`).
3. Chạy thử: `--network none`, `/data` gắn chỉ đọc (`:ro`), `--gpus all`; đo thời gian chạy hết bộ public và nhân 1,5 để dự phòng.
4. Chạy 2 lần, so từng câu: lệch phải ≤ 0,03 PA.
5. Quy trình nộp: `docker save` → nén → `sha256sum` → upload Google Drive → form "Solution Submission".
