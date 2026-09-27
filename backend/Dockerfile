FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 argus
WORKDIR /app
COPY --from=build --chown=argus:argus /app /app
COPY --chown=argus:argus alembic.ini docker-entrypoint.sh ./
COPY --chown=argus:argus migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 ARGUS_LOG_JSON=true
USER argus
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/ready', timeout=4)" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "--factory", "argus.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
