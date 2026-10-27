FROM ghcr.io/astral-sh/uv:0.13.6-python3.13-trixie@sha256:b72353db9e2060a798f2920910d453e96370eb0078ba79eee7c3befa90d255fb AS uv_source

FROM python:3.13.14-slim-bookworm@sha256:67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8 AS python_base
# Targeted security updates verified in the signed Debian Bookworm repository.
# CVE-2026-84782: retain the reviewed base digest and patch its OpenSSL pair.
RUN apt-get update && \
    apt-get install --yes --no-install-recommends --only-upgrade \
        libpcre2-8-0=10.42-1+deb12u2 perl-base=5.36.0-7+deb12u4 \
        libssl3=3.0.22-1~deb12u2 openssl=3.0.22-1~deb12u2 && \
    rm -rf /var/lib/apt/lists/*

FROM python_base AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY --from=uv_source /usr/local/bin/uv /usr/local/bin/uv
COPY services/control-api/pyproject.toml services/control-api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM dependencies AS test
RUN uv sync --frozen --no-install-project
WORKDIR /workspace
COPY . .
RUN find . -type f -exec chmod a-x {} +
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/workspace/services/control-api
CMD ["sh", "-c", "ruff check services/control-api/app services/control-api/tests tests && pytest -q"]

FROM python_base AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=dependencies --chown=10001:10001 /app/.venv /app/.venv
COPY --chown=10001:10001 services/control-api/app ./app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
