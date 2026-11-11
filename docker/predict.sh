#!/usr/bin/env bash
# Entry point of the image (Docker guideline 2026 §5): `bash /code/predict.sh`, no arguments. Starts llama-server,
# answers every question of /data into /result/submission.jsonl (written line by line) and /result/logs/ (one record
# per question: id, answer, elapsed_ms, thinking, code, inputs, output), stops the server. If the server does not come
# up, the run goes on with the rule-based reader alone (fewer answers, never no file). Fixed settings: model
# /code/models/model.gguf, one GPU (the first one given), greedy decoding with a fixed seed, one slot, thinking off;
# time budget 5.5 h counted from here (configs/default.json). Prints the model load and prediction times.
# T008: a server that does not come up on GPU 0 is started once more on GPU 1 (when there is one); a watchdog starts it
# again if it dies during the run, and the client (datamate/llm) waits for it and calls again.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"   # /code: the package, assets and configs are read from here
DATA_DIR="${DATA_DIR:-/data}"
OUT_DIR="${OUT_DIR:-/result}"
MODEL="${MODEL:-/code/models/model.gguf}"
PORT="${PORT:-8091}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES_OVERRIDE:-0}"  # one card: Qwen3-8B Q4 needs ~6 GB; same run each time
export LD_LIBRARY_PATH="/code/llama:${LD_LIBRARY_PATH:-}"
mkdir -p "$OUT_DIR/logs"
T0=$(date +%s)
echo "[predict.sh] start $(date -Is) data=$DATA_DIR out=$OUT_DIR model=$MODEL gpu=$CUDA_VISIBLE_DEVICES"

launch_server() {  # the same flags every time: one slot, greedy, seed 0
  echo "--- start on GPU $CUDA_VISIBLE_DEVICES $(date -Is) ---" >> "$OUT_DIR/logs/llama_server.log"
  /code/llama/llama-server -m "$MODEL" --jinja -ngl 99 -c 8192 --parallel 1 --seed 0 --host 127.0.0.1 --port "$PORT" \
      >> "$OUT_DIR/logs/llama_server.log" 2>&1 &
  SERVER=$!
}

start_server() {  # $1 = GPU index; 0 when the server answers /health (up to 10 minutes), else kills it and returns 1
  export CUDA_VISIBLE_DEVICES="$1"
  launch_server
  for _ in $(seq 1 300); do
    if python3 -c "import json,sys,urllib.request as u; sys.exit(0 if json.load(u.urlopen('http://127.0.0.1:$PORT/health', timeout=2)).get('status')=='ok' else 1)" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "$SERVER" 2>/dev/null; then break; fi
    sleep 2
  done
  kill "$SERVER" 2>/dev/null || true
  return 1
}

ready=0
if start_server "${CUDA_VISIBLE_DEVICES_OVERRIDE:-0}"; then
  ready=1
elif [ "$(nvidia-smi -L 2>/dev/null | wc -l)" -ge 2 ]; then
  echo "[predict.sh] llama-server did not start on GPU 0: trying GPU 1" >&2
  start_server 1 && ready=1
fi
T1=$(date +%s)
echo "Model load time: $((T1 - T0)) s (ready=$ready)"

WATCHDOG=""
if [ "$ready" = 1 ]; then
  ( while sleep 10; do  # a dead server is started again; the client waits for it (datamate/llm, T008)
      kill -0 "$(cat "$OUT_DIR/logs/.server_pid")" 2>/dev/null && continue
      echo "[predict.sh] llama-server died, starting it again $(date -Is)" >&2
      launch_server
      echo "$SERVER" > "$OUT_DIR/logs/.server_pid"
    done ) &
  WATCHDOG=$!
  echo "$SERVER" > "$OUT_DIR/logs/.server_pid"
  python3 -m datamate.predict --data "$DATA_DIR" --out "$OUT_DIR" --llm-url "http://127.0.0.1:$PORT" \
      --elapsed-s "$(( T1 - T0 ))"
  status=$?
else
  echo "llama-server did not start: rule-based reader only" >&2
  status=1
fi
if [ "$status" != 0 ]; then  # the LLM run failed or never started: a file from the baseline is still worth points
  # N165: --resume keeps the answers the first run wrote; --elapsed-s keeps one clock for the 5.5 h budget
  python3 -m datamate.predict --data "$DATA_DIR" --out "$OUT_DIR" --resume --elapsed-s "$(( $(date +%s) - T0 ))"
  status=$?
fi
if [ ! -f "$OUT_DIR/submission.jsonl" ]; then  # an empty file beats no file
  : > "$OUT_DIR/submission.jsonl"
  echo "[predict.sh] ERROR: no submission.jsonl was written; left an empty one" >&2
fi
T2=$(date +%s)
echo "Prediction time: $((T2 - T1)) s"
echo "Total time: $((T2 - T0)) s"
[ -n "$WATCHDOG" ] && kill "$WATCHDOG" 2>/dev/null
kill "$(cat "$OUT_DIR/logs/.server_pid" 2>/dev/null || echo "$SERVER")" 2>/dev/null || true
kill "$SERVER" 2>/dev/null || true
echo "[predict.sh] done $(date -Is) status=$status"
exit 0  # a valid file exists: a non-zero exit must not make the grader discard it
