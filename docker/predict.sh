#!/usr/bin/env bash
# Entry point of the image: start llama-server on the first GPU, answer every question of $DATA_DIR into
# $OUT_DIR/submission.jsonl, stop the server. If the server does not come up, the run goes on with the rule-based
# reader alone (fewer answers, never no file). The time budget (5.5 h, configs/default.json) counts from here.
# Prints the model load time and the prediction time to stdout (the 2025 Zalo AI Docker guideline asked for both).
set -uo pipefail
DATA_DIR="${DATA_DIR:-/data}"
OUT_DIR="${OUT_DIR:-/result}"
MODEL="${MODEL:-/models/model.gguf}"
PORT="${PORT:-8091}"
mkdir -p "$OUT_DIR"
T0=$(date +%s)

/opt/llama/llama-server -m "$MODEL" --jinja -ngl 99 -c 8192 --parallel 1 --host 127.0.0.1 --port "$PORT" \
    > "$OUT_DIR/llama_server.log" 2>&1 &
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
  python3 -m datamate.predict --data "$DATA_DIR" --out "$OUT_DIR" --llm-url "http://127.0.0.1:$PORT"
  status=$?
else
  echo "llama-server không lên: chạy bằng bộ đọc luật (baseline)" >&2
  status=1
fi
if [ "$status" != 0 ]; then  # the LLM run failed or never started: a file from the baseline is still worth points
  python3 -m datamate.predict --data "$DATA_DIR" --out "$OUT_DIR"
  status=$?
fi
T2=$(date +%s)
echo "Prediction time: $((T2 - T1)) s"
echo "Total time: $((T2 - T0)) s"
kill "$SERVER" 2>/dev/null || true
exit "$status"
