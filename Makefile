.PHONY: init config build up down logs ps health test lint smoke recovery-smoke agent-smoke backup agent-up local-model-up doctor clean

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

local-model-up:
	powershell -ExecutionPolicy Bypass -File scripts/local-model.ps1

doctor:
	powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1

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

recovery-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/recovery-smoke.ps1

agent-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/agent-smoke.ps1

backup:
	powershell -ExecutionPolicy Bypass -File scripts/backup.ps1

clean:
	docker compose down --remove-orphans
