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

---

## Bản nháp đã viết (04/11, kế hoạch §11): `docker/Dockerfile`, `docker/predict.sh`, `.dockerignore`

Bản này theo mặc định trong kế hoạch (CUDA 12.8, RTX 5090). Khi BTC gửi guideline thì sửa base image, đường dẫn `/data`, `/result` và lệnh chạy cho khớp. **Không build trên laptop**: base image CUDA nặng vài GB, mà laptop dùng mạng 4G (H20). Build trên máy RTX 5090 thuê dạng **VM** (container thuê không chạy được Docker bên trong).

### Buổi GPU (12/11), trên VM RTX 5090
```bash
# 0. máy: Ubuntu + driver NVIDIA ≥ 570 (CUDA 12.8), docker, nvidia-container-toolkit
nvidia-smi && docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi

# 1. code (git clone repo riêng tư, hoặc tải zip từ Drive) và model
git clone https://github.com/panno1vn/ZAIC && cd ZAIC
pip install -U huggingface_hub
huggingface-cli download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf --local-dir docker/models
sha256sum docker/models/*.gguf   # ghi lại, đối chiếu với trang Hugging Face

# 2. build (khoảng 15-25 phút; phần build llama.cpp chiếm nhiều nhất)
docker build -f docker/Dockerfile -t zaic-datamate:v1 --build-arg MODEL_FILE=Qwen3-8B-Q4_K_M.gguf .

# 3. chạy thử như BTC: không mạng, dữ liệu chỉ đọc, đo thời gian
mkdir -p /tmp/result
time docker run --rm --gpus all --network none -v "$PWD/data/public_test:/data:ro" -v /tmp/result:/result zaic-datamate:v1
python3 -m datamate.eval.validate --pred /tmp/result/submission.jsonl --split public_test
# so với lượt chạy trên laptop: cùng số câu trả lời, khác biệt ghi vào HAN_CHE (N4)

# 4. đóng gói và đẩy lên Google Drive
docker save zaic-datamate:v1 | gzip > zaic-datamate-v1.tar.gz
sha256sum zaic-datamate-v1.tar.gz > zaic-datamate-v1.sha256
rclone copy zaic-datamate-v1.tar.gz gdrive:ZAIC/ && rclone copy zaic-datamate-v1.sha256 gdrive:ZAIC/
```

### Những gì image chứa
- llama.cpp `llama-server` build cho sm_120 (Blackwell), tag `b12064` như trên laptop.
- Model GGUF ở `/models/model.gguf` (Qwen3-8B Q4_K_M, Apache 2.0; K1 ngày 06/11 chốt 8B: 14B không hơn rõ, chậm gấp đôi, xem HAN_CHE N49).
- `datamate/`, `assets/` (H14: kho ví dụ, từ điển nối tên, luật tham chiếu, mapping mẫu), `configs/`.
- `tools/` (thể lệ đòi mã "huấn luyện": các công cụ dựng lại `assets/` từ train) và `/app/README.md` (bản `docker/README_IMAGE.md`: cách chạy, phương pháp, tài sản dựng từ train, giấy phép).
- `predict.sh`: mở server, chạy `datamate.predict` trên `$DATA_DIR`, ghi `$OUT_DIR/submission.jsonl`. Server không lên thì chạy bộ đọc luật (baseline), vẫn có file nộp.

### Đối chiếu với hướng dẫn Docker năm 2025 (đề RoadBuddy)
Nguồn: [Scribd](https://www.scribd.com/document/950068255/zac2025-roadbuddy-docker-guideline). Trang chính bị khoá; nội dung lấy từ bản nhúng của Scribd, chỉ có phần tóm lược.
- **Máy chấm 2025:** driver 535.86.10, CUDA 12.2; base image mẫu `nvidia/cuda:12.2.0-devel-ubuntu22.04`. Năm 2026 máy chấm là RTX 5090, cần CUDA ≥ 12.8 và driver ≥ 570 (driver 535 không chạy được 5090), nên giữ CUDA 12.8. Khi có guideline 2026 thì đối chiếu lại phiên bản driver.
- **`predict.sh`** đọc `/data`, ghi `/result/submission.*`: đã khớp.
- **In ra màn hình thời gian nạp model và thời gian dự đoán:** đã thêm vào `predict.sh` (`Model load time`, `Prediction time`, `Total time`).
- **Nộp kèm `predict_notebook.ipynb`** để BTC đo thời gian: đã soạn `docker/predict_notebook.ipynb` (làm đúng các bước của `predict.sh`, in từng mốc thời gian), chép vào `/app`. Image không cài Jupyter; nếu BTC 2026 đòi chạy notebook trong container thì thêm `jupyter` vào image.
- **Cách làm năm 2025:** dựng container, chép code và model, `commit`, `save`. Mình dùng Dockerfile, ra cùng một image nhưng dựng lại được.
- **Hướng dẫn 2025 không nói:** lệnh `docker run` của BTC, giới hạn thời gian, dung lượng, mạng, cách nộp. Vẫn theo thể lệ 2026: không mạng, ≤ 6 giờ, nộp link Drive và checksum.

### Còn chờ
- Guideline BTC: base image bắt buộc, cấu trúc `/data` (`find_split_dir` nhận cả thư mục split lẫn thư mục cha), lệnh chạy, có cần ghi log hay không.
- Có dùng 2 card (2 server, chia cửa hàng) để chạy nhanh hơn hay không: chỉ cần nếu private đông câu.
