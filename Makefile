# Aegis developer Makefile. See README.md for the full local walkthrough.
.PHONY: help install infra-up infra-down topics db-init test lint \
        run-ingestion run-detection run-notification run-console demo

help:
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN{FS=":.*?# "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: # install package + dev deps (editable)
	pip install -e ".[dev]"

install-ai: # also install Phase 2/3 AI deps
	pip install -e ".[dev,ai]"

infra-up: # start backing stores + observability (docker compose)
	docker compose up -d postgres redis kafka qdrant otel-collector jaeger
	docker compose up kafka-init

infra-down: # stop all infra
	docker compose down

db-init: # create schema + seed catalog/policy
	python scripts/init_db.py

test: # run unit tests
	pytest -q

lint: # ruff + mypy
	ruff check src tests && mypy src

run-ingestion: # run Ingestion Gateway (:8001)
	python -m aegis_services.ingestion_gateway.app

run-detection: # run Detection & Correlation worker
	python -m aegis_services.detection.worker

run-notification: # run Notification worker
	python -m aegis_services.notification.worker

run-console: # run Console API (:8002)
	python -m aegis_services.console_api.app

demo: # send sample signals to a running gateway
	python scripts/send_demo_signals.py
