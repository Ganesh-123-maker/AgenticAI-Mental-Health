#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="${WEB_DIR:-${SCRIPT_DIR}/src/web}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env.local}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [ ! -f "${WEB_DIR}/main.py" ]; then
  echo "[ERROR] Backend entrypoint not found: ${WEB_DIR}/main.py"
  echo "[HINT] You can specify the web directory via WEB_DIR, for example:"
  echo "       WEB_DIR=/path/to/PsychAgent/src/web ./run_backend.sh"
  exit 1
fi

cd "${WEB_DIR}"

if [ -f requirements.txt ]; then
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt
fi

export PSYCHAGENT_WEB_BASELINE_CONFIG="${PSYCHAGENT_WEB_BASELINE_CONFIG:-configs/baselines/psychagent_sglang_local.yaml}"
export PSYCHAGENT_WEB_RUNTIME_CONFIG="${PSYCHAGENT_WEB_RUNTIME_CONFIG:-configs/runtime/psychagent_sglang_local.yaml}"
export DB_URL="${DB_URL:-sqlite:///$WEB_DIR/data.db}"

# Proxy bypass for internal endpoints.
NO_PROXY_EXTRA="${NO_PROXY_EXTRA:-35.220.164.252,10.102.252.187}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}${NO_PROXY_EXTRA}"
export no_proxy="${no_proxy:+$no_proxy,}${NO_PROXY_EXTRA}"

# Required keys for the default baseline/runtime config.
export SGLANG_API_KEY="${SGLANG_API_KEY:-EMPTY}"
if [ -z "${PSYCHAGENT_EMBEDDING_API_KEY:-}" ]; then
  echo "[ERROR] Missing PSYCHAGENT_EMBEDDING_API_KEY."
  echo "[HINT] You can set it in ~/.bashrc, ~/.zshrc, or ${ENV_FILE}, for example:"
  echo "       export PSYCHAGENT_EMBEDDING_API_KEY='your-key'"
  exit 1
fi

uvicorn main:app --reload --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
