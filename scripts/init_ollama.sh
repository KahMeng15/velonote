#!/bin/sh
# ==============================================================================
# Velonote — Ollama Automatic First-Startup Configuration Script
#
# Automatically waits for Ollama to be available, checks if the model exists,
# and pulls the lightweight model (default: qwen2.5:1.5b) if missing.
# ==============================================================================

set -e

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"

echo "[velonote-ollama] Target Ollama Host: ${OLLAMA_HOST}"
echo "[velonote-ollama] Target Model: ${OLLAMA_MODEL}"

# 1. Wait for Ollama service to be ready
echo "[velonote-ollama] Waiting for Ollama API to be reachable..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if curl -s -f "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "[velonote-ollama] Ollama is online!"
    break
  fi
  RETRY_COUNT=$((RETRY_COUNT + 1))
  echo "[velonote-ollama] Waiting for Ollama... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 3
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
  echo "[velonote-ollama] ERROR: Timed out waiting for Ollama at ${OLLAMA_HOST}"
  exit 1
fi

# 2. Check if model already exists
echo "[velonote-ollama] Checking if model '${OLLAMA_MODEL}' is already downloaded..."
TAGS_RESPONSE=$(curl -s "${OLLAMA_HOST}/api/tags" || true)

if echo "$TAGS_RESPONSE" | grep -q "\"name\":\"${OLLAMA_MODEL}"; then
  echo "[velonote-ollama] Model '${OLLAMA_MODEL}' already exists. Skipping download."
  exit 0
fi

# 3. Pull the model
echo "[velonote-ollama] Model not found. Pulling '${OLLAMA_MODEL}' (this happens once on initial setup)..."
PULL_PAYLOAD="{\"name\": \"${OLLAMA_MODEL}\"}"

curl -s -N -X POST "${OLLAMA_HOST}/api/pull" -d "$PULL_PAYLOAD" | while IFS= read -r line; do
  STATUS=$(echo "$line" | grep -o '"status":"[^"]*"' | cut -d'"' -f4 || true)
  if [ -n "$STATUS" ]; then
    printf "\r[velonote-ollama] Status: %s" "$STATUS"
  fi
done

echo ""
echo "[velonote-ollama] Successfully pulled and verified '${OLLAMA_MODEL}'!"
exit 0
