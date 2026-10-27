FROM ghcr.io/astral-sh/uv:0.13.6-python3.13-trixie@sha256:b72353db9e2060a798f2920910d453e96370eb0078ba79eee7c3befa90d255fb AS uv_source

FROM mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0 AS runtime
# Ubuntu USN-8847-1: targeted OpenSSL fix, retaining the reviewed Playwright digest.
RUN apt-get update && \
    apt-get install --yes --no-install-recommends --only-upgrade \
        libssl3t64=3.0.13-0ubuntu3.16 openssl=3.0.13-0ubuntu3.16 && \
    rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=uv_source /usr/local/bin/uv /usr/local/bin/uv
COPY services/action-worker/pyproject.toml services/action-worker/uv.lock ./
# Remove unused system provisioning tools and the orphaned virtualenv dependency pair.
RUN uv sync --frozen --no-dev --no-install-project && \
    /usr/bin/python3 -m pip uninstall --yes --break-system-packages virtualenv python-discovery filelock && \
    /usr/bin/python3 -m pip check && \
    /usr/bin/python3 -m pip uninstall --yes --break-system-packages pip && \
    rm -rf /tmp/uv-cache /root/.cache && \
    chown -R pwuser:pwuser /app
COPY --chown=pwuser:pwuser services/control-api/app ./app
USER pwuser
CMD ["python", "-m", "app.action_worker"]
