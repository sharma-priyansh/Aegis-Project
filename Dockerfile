# Single image for all Aegis Python services; the entrypoint selects which one to run.
# Multi-stage keeps the runtime lean. Used by docker-compose --profile app and K8s.
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip build && pip wheel --wheel-dir /wheels ".[ai]"

FROM base AS runtime
COPY --from=builder /wheels /wheels
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-index --find-links=/wheels ".[ai]" && rm -rf /wheels
# Default to the console; override `command:` per service in compose/K8s.
ENV PORT=8002
CMD ["python", "-m", "aegis_services.console_api.app"]
