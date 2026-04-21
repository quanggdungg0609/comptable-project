#!/bin/bash
set -e

MODEL_DIR="/models"
MODEL_FILE="$MODEL_DIR/gemma-4-e2b-it-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/bartowski/gemma-4-e2b-it-GGUF/resolve/main/gemma-4-e2b-it-Q4_K_M.gguf"

mkdir -p "$MODEL_DIR"

if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading gemma-4-e2b-it-Q4_K_M.gguf (~1.5GB)..."
    if [ -z "$HF_TOKEN" ]; then
        echo "ERROR: HF_TOKEN is required to download Gemma (gated model)."
        echo "Set HF_TOKEN in .env and accept terms at huggingface.co/google/gemma-4-e2b-it"
        exit 1
    fi
    curl -L --progress-bar -H "Authorization: Bearer $HF_TOKEN" -o "$MODEL_FILE.tmp" "$MODEL_URL"
    mv "$MODEL_FILE.tmp" "$MODEL_FILE"
    echo "Download complete!"
else
    echo "Model already present, skipping download."
fi

echo "Starting llama.cpp server..."
exec /llama-server \
    -m "$MODEL_FILE" \
    --host 0.0.0.0 \
    --port 8080 \
    --ctx-size 8192 \
    --threads 4 \
    -ngl 0
