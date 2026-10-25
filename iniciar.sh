#!/usr/bin/env bash
# Arranca el editor de materias extrañas (macOS / Linux). La primera vez instala lo necesario.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m streamlit run streamlit_app.py --server.maxUploadSize 2000 --browser.gatherUsageStats false
