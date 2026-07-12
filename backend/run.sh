#!/usr/bin/env bash
# Start the Ekosight CEO Agent V1 backend + dashboard.
set -euo pipefail
cd "$(dirname "$0")"
pip install -q -r requirements.txt
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
