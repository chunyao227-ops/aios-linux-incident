#!/bin/sh
set -eu

python /opt/demo/control.py initialize
python /opt/demo/dependency.py >/tmp/demo-dependency.log 2>&1 &
echo "$!" >/run/demo/dependency.pid
exec python /opt/demo/server.py
