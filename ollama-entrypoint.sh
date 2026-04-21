#!/bin/bash
set -e

# Start Ollama in background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready (check port 11434 using netcat)
echo "Waiting for Ollama to be ready..."
for i in {1..60}; do
  if nc -z localhost 11434 2>/dev/null; then
    echo "Ollama is ready!"
    sleep 2  # Give it a moment to fully initialize API
    break
  fi
  echo "Attempt $i/60: Ollama not ready yet, waiting..."
  sleep 1
done

# Pull qwen3.5:4b model
echo "Pulling qwen3:1.7b model..."
/bin/ollama pull qwen3:1.7b

echo "Ollama setup complete!"

# Keep Ollama running in foreground
wait $OLLAMA_PID
