.DEFAULT_GOAL := help
SANDBOX_IMAGE ?= glimpse-sandbox

.PHONY: help sandbox dev test test-docker test-all lint format up down prod prod-logs prod-down lambda-build lambda-local lambda-smoke demo clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sandbox: ## Build the sandbox image (toolchains only)
	docker build -t $(SANDBOX_IMAGE) sandbox/

dev: ## Run the API locally with auto-reload (needs `make sandbox` for the docker runner)
	uv run glimpse serve --reload

test: ## Unit tests (no Docker needed)
	uv run pytest -m "not docker"

test-docker: ## Integration tests against a real Docker daemon + sandbox image
	GLIMPSE_REQUIRE_DOCKER=1 uv run pytest -m docker

test-all: ## Everything
	uv run pytest

lint: ## ruff + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format: ## Auto-format and fix lint
	uv run ruff format .
	uv run ruff check --fix .

up: ## One-command local stack: build sandbox + API, serve on :8000
	docker compose up --build

down: ## Stop the local stack
	docker compose down

PROD_COMPOSE = docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml

prod: ## Public instance: build + (re)start API, sandbox image and Caddy (see docs/deploy.md)
	$(PROD_COMPOSE) up -d --build --remove-orphans
	docker image prune -f

prod-logs: ## Follow the public instance's logs
	$(PROD_COMPOSE) logs -f --tail=100

prod-down: ## Stop the public instance
	$(PROD_COMPOSE) down

lambda-build: ## Build the Lambda container image
	docker build -f lambda/Dockerfile -t glimpse-lambda .

lambda-local: ## Run the Lambda image locally with the Runtime Interface Emulator on :9000
	docker run --rm -p 9000:8080 glimpse-lambda

lambda-smoke: ## Invoke every language through a running `make lambda-local`
	python3 lambda/smoke_test.py

demo: ## Build the web demo
	cd demo && npm ci && npm run build

clean: ## Remove caches, build output and leaked sandbox containers
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist demo/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	-docker ps -aq --filter label=glimpse.sandbox=1 | xargs docker rm -f
