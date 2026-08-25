.PHONY: init config build up dashboard down logs ps health test lint smoke career-smoke side-effect-smoke recovery-smoke lifecycle-smoke agent-smoke backup restore-drill readiness agent-up local-model-up side-effects-up doctor clean

init:
	powershell -ExecutionPolicy Bypass -File scripts/init-env.ps1

config:
	docker compose config --quiet

build:
	docker compose build control-api dispatcher worker

up:
	docker compose up -d --build

dashboard:
	powershell -ExecutionPolicy Bypass -File scripts/open-dashboard.ps1 -LocalModel -CopyToken

agent-up:
	docker compose --profile agent up -d

local-model-up:
	powershell -ExecutionPolicy Bypass -File scripts/local-model.ps1

side-effects-up:
	powershell -ExecutionPolicy Bypass -File scripts/up.ps1 -SideEffects

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

career-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/career-smoke.ps1 -Draft

side-effect-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/side-effect-smoke.ps1

recovery-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/recovery-smoke.ps1

lifecycle-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/lifecycle-smoke.ps1

agent-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/agent-smoke.ps1

backup:
	powershell -ExecutionPolicy Bypass -File scripts/backup.ps1

restore-drill:
	powershell -ExecutionPolicy Bypass -File scripts/restore-drill.ps1

readiness:
	powershell -ExecutionPolicy Bypass -File scripts/readiness.ps1

clean:
	docker compose down --remove-orphans
