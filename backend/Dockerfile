FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic alembic
COPY kickpick kickpick
RUN groupadd --gid 10001 kickpick && useradd --uid 10001 --gid kickpick --no-create-home kickpick
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001

FROM base AS ml
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --no-install-project --extra ml
RUN mkdir /state && chown 10001:10001 /state
ENV MPLCONFIGDIR=/tmp/matplotlib OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
USER 10001:10001

# The default API/collector image keeps its small dependency set.
FROM base AS runtime
