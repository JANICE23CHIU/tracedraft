#!/usr/bin/env sh
# Stage II on the ASUS UGen300 (Hailo-10H) via hailo-ollama. UNTESTED until the device arrives.
# 1) start hailo-ollama (see hailo_model_zoo_genai docs); default port 8000
# 2) list models and set MODEL to the Qwen2.5-1.5B-Instruct name it reports:
#      curl http://127.0.0.1:8000/hailo/v1/list
set -e
cd "$(dirname "$0")/.."
MODEL=${MODEL:?set MODEL to the hailo-ollama model name}
python3 -B -m tracedraft ping --adapter hailo --base-url http://127.0.0.1:8000 --model "$MODEL"
for C in K1 F2; do
  python3 -B -m tracedraft run --case $C --style prose --selector fcea --adapter hailo --base-url http://127.0.0.1:8000 --model "$MODEL"
  python3 -B -m tracedraft verifier-eval --case $C --style prose --adapter hailo --base-url http://127.0.0.1:8000 --model "$MODEL" --llm-mode review
done
