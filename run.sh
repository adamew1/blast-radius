#!/usr/bin/env bash
# Blast Radius — launch the dashboard (macOS/Linux). Cache-first; works offline from data/raw/.
# Strict offline: BLAST_RADIUS_OFFLINE=1 ./run.sh
set -e
cd "$(dirname "$0")"
exec .venv/bin/streamlit run app/Home.py
