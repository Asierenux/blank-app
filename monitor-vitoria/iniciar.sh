#!/usr/bin/env bash
# Arranca el monitor (recogida + panel). La primera vez prepara el entorno.
# Uso: ./iniciar.sh   ó   ./iniciar.sh --demo
set -e
cd "$(dirname "$0")"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "No encuentro Python. Instálalo desde https://www.python.org/downloads/"
  read -r -p "Pulsa Enter para salir" _; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Primera vez: preparando el entorno..."
  "$PY" -m venv .venv
fi
if ! cmp -s requirements.txt .venv/requisitos-instalados.txt; then
  echo "Instalando librerías, espera un momento..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
  cp requirements.txt .venv/requisitos-instalados.txt
fi
exec .venv/bin/python -m monitor_vitoria iniciar "$@"
