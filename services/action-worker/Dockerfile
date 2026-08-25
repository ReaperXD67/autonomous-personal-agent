FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie@sha256:7527c447eefbe4aa1ab927a0cd25c4f8224f9dd29ef53091679031ab3f069f66 AS uv_source

FROM mcr.microsoft.com/playwright/python:v1.62.0-noble@sha256:aa81288e738725378becba5b3e06cb0f3a7f012a610e87e8d767a090ea3f740d AS runtime
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
    rm -rf /tmp/uv-cache && \
    chown -R pwuser:pwuser /app
COPY --chown=pwuser:pwuser services/control-api/app ./app
USER pwuser
CMD ["python", "-m", "app.action_worker"]
