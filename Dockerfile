# syntax=docker/dockerfile:1
# Glimpse API image. Contains the API only -- no language toolchains, no user code.
# With GLIMPSE_RUNNER=docker it needs the host's Docker socket mounted (see
# docker-compose.yml) so it can create sandbox containers from `glimpse-sandbox`.

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.7.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    GLIMPSE_HOST=0.0.0.0 \
    GLIMPSE_PORT=8000

WORKDIR /app

# Dependencies first (cached unless the lockfile changes), then the package.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY glimpse ./glimpse
COPY lambda_handler.py ./
RUN uv sync --frozen --no-dev

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["glimpse", "serve"]
