.PHONY: init config build up down logs ps health test lint smoke backup agent-up free-models clean

init:
	powershell -ExecutionPolicy Bypass -File scripts/init-env.ps1

config:
	docker compose config --quiet

build:
	docker compose build control-api dispatcher worker

up:
	docker compose up -d --build

agent-up:
	docker compose --profile agent up -d

free-models:
	powershell -ExecutionPolicy Bypass -File scripts/configure-free-models.ps1

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

health:
	powershell -ExecutionPolicy Bypass -File scripts/health.ps1

test:
	docker compose --profile tools run --rm test

lint:
	docker compose --profile tools run --rm test ruff check services/control-api/app services/control-api/tests tests

smoke:
	powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1

backup:
	powershell -ExecutionPolicy Bypass -File scripts/backup.ps1

clean:
	docker compose down --remove-orphans
