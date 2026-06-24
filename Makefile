.PHONY: install dev up down run ui worker test lint fmt clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

up:
	docker compose up -d postgres redis chromadb

down:
	docker compose down

run:
	python -m orchestrator.main "$(TASK)"

ui:
	streamlit run ui/review_app.py

worker:
	celery -A orchestrator.worker.celery_app worker --loglevel=info

test:
	pytest -q

lint:
	ruff check src tests

fmt:
	ruff format src tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ chroma_data
