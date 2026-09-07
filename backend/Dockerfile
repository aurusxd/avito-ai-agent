FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app

# DISPLAY lives in the image env so that docker exec sessions (the login doctor,
# ad hoc debugging) reach the same virtual display the server uses
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    DISPLAY_NUM=99 \
    DISPLAY=:99

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# the browser download needs no apt, so it goes first and survives apt edits
RUN playwright install chromium

# xvfb-run needs xauth, and install-deps needs the package lists that the
# cleanup at the end removes, so both share one apt transaction.
# x11vnc and novnc let an operator finish a captcha in the bot's own browser.
RUN echo 'Acquire::Retries "8";' > /etc/apt/apt.conf.d/80-retries \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth x11vnc novnc websockify \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN uv sync --frozen --no-dev

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000 6080

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
