FROM ghcr.io/astral-sh/uv:0.9.2-python3.12-bookworm-slim AS base

RUN apt-get update && apt-get install -y \
  curl \
  bash \
  && apt upgrade openssl -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
  && useradd --system --gid 999 --uid 999 --create-home nonroot

FROM base AS dependencies
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --locked --no-install-project --no-dev --extra sentry

FROM dependencies AS app
COPY ../.. /app

RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev --extra sentry

ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

EXPOSE 8000

USER nonroot

CMD ["python", "main.py"]
