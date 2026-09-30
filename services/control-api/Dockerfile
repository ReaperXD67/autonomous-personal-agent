FROM ghcr.io/astral-sh/uv:0.12.3-python3.13-trixie@sha256:8e231456b9e5eab17151e10ca096b8a3d52936be045d6a48e006bede5f229a9a AS uv_source

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS python_base
# Debian's targeted fix for CVE-2026-86145 and CVE-2026-89161.
RUN apt-get update && \
    apt-get install --yes --no-install-recommends --only-upgrade libpcre2-8-0=10.42-1+deb12u1 && \
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
