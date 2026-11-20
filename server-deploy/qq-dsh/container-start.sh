#!/bin/sh
set -eu
umask 077
ulimit -c 0
export HOME=/app
export DISPLAY=:1
export XDG_CONFIG_HOME=/app/.config
export XDG_CACHE_HOME=/app/.cache
export XDG_RUNTIME_DIR=/tmp/qq-runtime
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :1 -screen 0 1080x760x16 +extension GLX +render >/tmp/xvfb.log 2>&1 &
sleep 2
cd /app/napcat
exec dbus-run-session -- /opt/QQ/qq --no-sandbox --disable-gpu -q 1000000003
