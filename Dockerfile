# Hardened multi-stage image for all Aegis Python services.
# Non-root, no build tools in the runtime layer, pinned base. The entrypoint selects
# which service to run via `command:` in compose/K8s (ADR-013: one image, many services).
FROM python:3.11-slim AS builder
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[ai]"

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
# Create an unprivileged user (hardening, §13).
RUN groupadd --gid 10001 aegis && useradd --uid 10001 --gid aegis --no-create-home aegis
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
COPY pyproject.toml README.md ./
USER 10001
# Default entrypoint; override per service. Health is checked by the platform (K8s probes).
ENV PORT=8002
CMD ["python", "-m", "aegis_services.console_api.app"]
