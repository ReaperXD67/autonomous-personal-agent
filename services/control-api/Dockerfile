FROM ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:b3c543b6c4f23a5f2df22866bd7857e5d304b67a564f4feab6ac22044dde719b AS uv_source

FROM python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576 AS dependencies
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

FROM python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576 AS runtime
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
