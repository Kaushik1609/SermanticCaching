.PHONY: setup db-up db-down migrate run test eval

setup:
	pip install -r requirements.txt
	@if not exist .env copy .env.example .env

db-up:
	docker compose up -d

db-down:
	docker compose down

migrate:
	python -m backend.engine.store.migrate

run:
	uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest backend/tests -v

eval:
	python scripts/threshold_sweep.py && python scripts/benchmark_latency.py
