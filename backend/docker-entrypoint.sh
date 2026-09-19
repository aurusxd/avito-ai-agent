#!/bin/sh
set -e

# avito detects headless chromium, so the browser runs headed against a virtual
# display. Xvfb is started as a daemon instead of wrapping the server in
# xvfb-run, which does not reliably exec its command as PID 1.
DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN="${XVFB_SCREEN:-1440x900x24}"

Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN}" -nolisten tcp &
XVFB_PID=$!

export DISPLAY=":${DISPLAY_NUM}"

for _ in $(seq 1 50); do
    if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
        break
    fi
    sleep 0.1
done

if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
    echo "Xvfb failed to start on ${DISPLAY}" >&2
    exit 1
fi

echo "Xvfb ready on ${DISPLAY} (pid ${XVFB_PID})"

# noVNC lets an operator finish a captcha by hand in the very browser the bot
# drives. It is off unless asked for, and never starts without a password: the
# display holds a signed-in avito session.
if [ "${VNC_ENABLED:-false}" = "true" ]; then
    if [ -z "${VNC_PASSWORD:-}" ]; then
        echo "VNC_ENABLED=true but VNC_PASSWORD is empty, refusing to expose the browser" >&2
        exit 1
    fi

    mkdir -p /root/.vnc
    x11vnc -storepasswd "${VNC_PASSWORD}" /root/.vnc/passwd >/dev/null 2>&1

    x11vnc -display "${DISPLAY}" -rfbauth /root/.vnc/passwd -rfbport 5900 \
        -localhost -forever -shared -noxdamage -quiet &
    echo "x11vnc listening on 127.0.0.1:5900"

    websockify --web=/usr/share/novnc "0.0.0.0:${VNC_WEB_PORT:-6080}" \
        "localhost:5900" >/dev/null 2>&1 &
    echo "noVNC ready on port ${VNC_WEB_PORT:-6080}"
fi

alembic upgrade head

# showcase build: fill the panel with believable data on first boot
if [ "${DEMO_MODE:-false}" = "true" ]; then
    echo "demo mode: seeding showcase data"
    python -m app.db.demo_seed
fi

exec "$@"
