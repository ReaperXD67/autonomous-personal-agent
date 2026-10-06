FROM ghcr.io/astral-sh/uv:0.12.23-python3.13-trixie@sha256:8638cb5839a13bb229746704507a38ea7bfa01d1140aabe85dad35ed27de6ce3 AS uv_source

FROM mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=uv_source /usr/local/bin/uv /usr/local/bin/uv
COPY services/action-worker/pyproject.toml services/action-worker/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && \
    /usr/bin/python3 -m pip uninstall --yes --break-system-packages virtualenv pip && \
    rm -rf /tmp/uv-cache /root/.cache && \
    chown -R pwuser:pwuser /app
COPY --chown=pwuser:pwuser services/control-api/app ./app
USER pwuser
CMD ["python", "-m", "app.action_worker"]
