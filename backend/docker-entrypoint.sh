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

alembic upgrade head

exec "$@"
