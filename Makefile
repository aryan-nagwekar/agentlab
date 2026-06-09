.PHONY: help install test api web demo build up seed-docker down logs

VENV ?= .venv
PY   := $(VENV)/bin/python

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## create venv, install api + sdk (editable) and web deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -e "apps/api[dev]" -e "packages/sdk-python[dev]"
	cd apps/web && npm install

test: ## run backend + SDK test suites
	$(PY) -m pytest apps/api/tests packages/sdk-python/tests -q

api: ## run the collector on :8000 (SQLite, hot reload)
	cd apps/api && ../../$(VENV)/bin/python -m uvicorn app.main:app --reload --port 8000

web: ## run the dashboard dev server on :5173
	cd apps/web && npm run dev

demo: ## seed three demo runs into the local collector
	$(PY) examples/basic_multi_agent/run_demo.py --fast

build: ## production build of the dashboard
	cd apps/web && npm run build

up: ## full stack via docker compose (postgres + api + web on :3000)
	docker compose up --build -d

seed-docker: ## seed demo runs inside docker
	docker compose --profile demo run --rm seed

down: ## stop the docker stack
	docker compose down

logs: ## tail docker logs
	docker compose logs -f api web
