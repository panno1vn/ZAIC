#!/usr/bin/env bash
# Trên VM, sau vm_build.sh đạt: đóng gói image, tải lên Drive, kiểm MD5 trên Drive, in link + MD5 để nộp.
#   TEAM=band DIR=v2 bash ~/work/vm_pack.sh 2>&1 | tee ~/work/pack.log
# 11/11: rclone dùng client_id chung bị Google rateLimitExceeded; mảnh 8 MB (mặc định) làm file 6,8 GB tải lại từ đầu
# 3 lần. Mảnh 256 MB + tpslimit 3: 3 phút, 40 MiB/s.
set -euo pipefail
: "${TEAM:?Đặt tên đội trước: TEAM=<ten_doi> DIR=<v2> bash vm_pack.sh}"
: "${DIR:?Đặt thư mục Drive: DIR=v2}"
IMG="zaic2026_datamate_${TEAM}:final"
F="zaic2026_datamate_${TEAM}.tar.gz"
DST="gdrive:ZAIC_docker/${DIR}"
UP=(--drive-chunk-size 256M --tpslimit 3 --retries 10 --low-level-retries 50 --stats 30s --stats-one-line -v)
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
cd ~/work
step() { echo; echo "===== $(date +%H:%M:%S) $* ====="; }

step "1. docker save | pigz"
time $SUDO docker save "$IMG" | pigz -p "$(nproc)" > "$F"
ls -la "$F"
TAR_BYTES=$(pigz -dc "$F" | wc -c)
md5sum "$F" | tee "$F.md5"
MD5=$(cut -d' ' -f1 "$F.md5")

step "2. Tải lên Drive ($DST)"
tar czf "runs_${DIR}.tgz" r1 r2 build.log compare_r1.txt compare_r2.txt ZAIC/docker/README_IMAGE.md ZAIC/docker/Dockerfile
rclone copy "$F" "$DST" "${UP[@]}" 2>&1 | { grep -v client_id || true; }
rclone copy "$F.md5" "$DST" "${UP[@]}" 2>&1 | { grep -v client_id || true; }
rclone copy "runs_${DIR}.tgz" "$DST" "${UP[@]}" 2>&1 | { grep -v client_id || true; }

step "3. Kiểm MD5 trên Drive"
REMOTE=$(rclone md5sum "$DST/$F" 2>/dev/null | cut -d' ' -f1)
echo "local=$MD5 drive=$REMOTE"
[ "$MD5" = "$REMOTE" ] || { echo "MD5 KHÁC: tải lên lại, chưa nộp"; exit 1; }

step "4. Link chia sẻ"
rclone link "$DST/$F" 2>/dev/null
ID=$(rclone lsjson "$DST/$F" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['ID'])")
echo
echo "Google url : https://drive.google.com/file/d/$ID/view"
echo "Checksum MD5: $MD5"
echo "Số byte .tar chưa nén: $TAR_BYTES"
echo "Mở link trong cửa sổ ẩn danh, rồi nộp ở Test Solution. Xong: rm ~/.config/rclone/rclone.conf, Destroy VM."
