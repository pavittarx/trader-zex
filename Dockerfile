# syntax=docker/dockerfile:1.7
# Self-contained image for the trader-zex pipeline. Multi-stage: deps resolve in
# a uv builder, the runtime stage carries only the venv + source (no toolchain).
# Secrets are NEVER baked in — pass Fyers creds at runtime (env / mounted token).

# ---- builder: resolve locked deps into /app/.venv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# Deps only (not the project itself) — cached on the lockfile, so source edits
# don't reinstall the world.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- runtime: slim, no build tools ----
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
# libgomp1: OpenMP runtime needed by scipy/scikit-learn/hmmlearn wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 trader
WORKDIR /app
COPY --from=builder --chown=trader:trader /app/.venv /app/.venv
COPY --chown=trader:trader . /app
USER trader

# Default: list strategies + stages. Override the args to run anything, e.g.:
#   docker run ... trader-zex -m runners.sandbox pead
#   docker run ... trader-zex -m strategies.momentum.research.momentum_ic --github --universe all --pit-top-k 200
ENTRYPOINT ["python"]
CMD ["-m", "runners.list"]
