#!/usr/bin/env bash
set -euo pipefail

echo "===== INSTALL LLAMA.CPP ====="

LLAMA_VERSION="b10516"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_VERSION}/llama-${LLAMA_VERSION}-bin-ubuntu-x64.tar.gz"

mkdir -p "$HOME/llama"
cd "$HOME/llama"

wget -q --show-progress "$LLAMA_URL" -O llama.tar.gz
tar -xzf llama.tar.gz --strip-components=1

echo "===== LLAMA FILES ====="
find . -maxdepth 2 -type f -name 'llama-server*' -o -name 'llama-cli*' | sort

echo "===== DOWNLOAD QWEN3 1.7B ====="

mkdir -p model

wget -q --show-progress \
  "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf" \
  -O model/Qwen3-1.7B-Q4_K_M.gguf

ls -lh model/Qwen3-1.7B-Q4_K_M.gguf

echo "===== START LLAMA SERVER ====="

./llama-server \
  -m model/Qwen3-1.7B-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 2048 \
  -t 4 \
  -ngl 0 \
  > llama.log 2>&1 &

LLAMA_PID=$!

echo "$LLAMA_PID" > llama.pid

echo "===== WAIT FOR LLAMA ====="

READY=0

for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
        echo "Llama server READY"
        READY=1
        break
    fi

    if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo "ERROR: llama-server mati."
        echo "===== LLAMA LOG ====="
        cat llama.log || true
        exit 1
    fi

    echo "Menunggu llama-server... $i/60"
    sleep 2
done

if [ "$READY" -ne 1 ]; then
    echo "ERROR: llama-server tidak ready setelah 120 detik."
    echo "===== LLAMA LOG ====="
    cat llama.log || true
    exit 1
fi

curl -sf http://127.0.0.1:8080/health

echo
echo "===== TEST LUNA AI ====="

curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "system",
        "content": "Kamu adalah Luna, komentator balap Indonesia yang kocak, heboh, spontan, sedikit nge-roast tapi ramah. Jawab maksimal satu kalimat pendek."
      },
      {
        "role": "user",
        "content": "Nissan GTR baru saja menyalip Ferrari. Komentari kejadian ini."
      }
    ],
    "temperature": 0.9,
    "top_p": 0.9,
    "max_tokens": 50,
    "stream": false
  }'

echo
echo
echo "===== LLAMA TEST SELESAI ====="
