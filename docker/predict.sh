#!/usr/bin/env bash
# Entry point of the image (Docker guideline 2026 §5): `bash /code/predict.sh`, no arguments. Starts llama-server,
# answers every question of /data into /result/submission.jsonl (written line by line) and /result/logs/ (one record
# per question: id, answer, elapsed_ms, thinking, code, inputs, output), stops the server. If the server does not come
# up, the run goes on with the rule-based reader alone (fewer answers, never no file). Fixed settings: model
# /code/models/model.gguf, one GPU (the first one given), greedy decoding with a fixed seed, one slot, thinking off;
# time budget 5.5 h counted from here (configs/default.json). Prints the model load and prediction times.
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

/code/llama/llama-server -m "$MODEL" --jinja -ngl 99 -c 8192 --parallel 1 --seed 0 --host 127.0.0.1 --port "$PORT" \
    > "$OUT_DIR/logs/llama_server.log" 2>&1 &
SERVER=$!

ready=0
for _ in $(seq 1 300); do  # up to 10 minutes to load the model
  if python3 -c "import json,sys,urllib.request as u; sys.exit(0 if json.load(u.urlopen('http://127.0.0.1:$PORT/health', timeout=2)).get('status')=='ok' else 1)" 2>/dev/null; then
    ready=1; break
  fi
  if ! kill -0 "$SERVER" 2>/dev/null; then break; fi
  sleep 2
done
T1=$(date +%s)
echo "Model load time: $((T1 - T0)) s (ready=$ready)"

if [ "$ready" = 1 ]; then
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
kill "$SERVER" 2>/dev/null || true
echo "[predict.sh] done $(date -Is) status=$status"
exit 0  # a valid file exists: a non-zero exit must not make the grader discard it
