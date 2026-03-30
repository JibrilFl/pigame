#!/usr/bin/env bash
set -e
cd /home/pizero/pigame
export PYTHONPATH=/home/pizero/pigame/src
exec /home/pizero/pigame/.venv/bin/python -m pigame.runtime \
  --renderer waveshare \
  --battery-backend cw2015 \
  --battery-bus 1 \
  --battery-address 0x62 \
  --low-battery-percent 15 \
  --critical-battery-percent 5 \
  --shutdown-command "systemctl poweroff" \
  --tick-seconds 180 \
  --save /home/pizero/pigame/data/save.json
