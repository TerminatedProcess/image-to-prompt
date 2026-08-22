#!/usr/bin/env bash
# Launch image-to-prompt wired to the local Unsloth vision server.
# Pulls the API key live from Unsloth's own auth file so it can never go stale.
set -euo pipefail
cd "$(dirname "$0")"

KEY_FILE="$HOME/.unsloth/studio/auth/agent_api_key.json"
if [[ -f "$KEY_FILE" ]]; then
  LMSTUDIO_API_KEY="$(python3 -c "import json,sys; d=json.load(open('$KEY_FILE')); print(next(iter(d['servers'].values()))['minted'][0])" 2>/dev/null || true)"
fi
if [[ -z "${LMSTUDIO_API_KEY:-}" ]]; then
  echo "WARNING: no Unsloth API key found at $KEY_FILE — the app will 401 against localhost:8889" >&2
fi
export LMSTUDIO_API_KEY

exec ./venv/bin/streamlit run app.py --server.port 8504 --server.headless true
