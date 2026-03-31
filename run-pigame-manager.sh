#!/usr/bin/env bash
set -e
cd /home/pizero/pigame
export PYTHONPATH=/home/pizero/pigame/src
exec /home/pizero/pigame/.venv/bin/python -m pigame.desktop_server \
  --host 0.0.0.0 \
  --port 8080 \
  --save /home/pizero/pigame/data/save.json
