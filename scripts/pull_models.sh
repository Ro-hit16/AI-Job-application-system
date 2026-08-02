#!/usr/bin/env bash
# =============================================================================
# pull_models.sh — Download required Ollama models
# Run AFTER Ollama is started: bash scripts/pull_models.sh
# =============================================================================

OLLAMA_URL="${OLLAMA_HOST:-http://localhost:11434}"
LLM_MODEL="${LLM_MODEL:-llama3}"
EMBED_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"

echo "Pulling LLM model: $LLM_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\":\"$LLM_MODEL\"}" | tail -1

echo "Pulling embedding model: $EMBED_MODEL"
curl -s "$OLLAMA_URL/api/pull" -d "{\"name\":\"$EMBED_MODEL\"}" | tail -1

echo ""
echo "Available models:"
curl -s "$OLLAMA_URL/api/tags" | python3 -c "import json,sys; [print(' -', m['name']) for m in json.load(sys.stdin).get('models',[])]"
echo "Done!"