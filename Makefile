.PHONY: init config build up dashboard down logs ps health test lint smoke career-smoke side-effect-smoke creator-outreach-smoke recovery-smoke lifecycle-smoke agent-smoke openrouter backup restore-drill readiness agent-up local-model-up side-effects-up doctor vps-init vps-preflight vps-up vps-smoke vps-local-model vps-model-health vps-dashboard-login vps-install-service vps-backup vps-restore-drill clean

init:
	powershell -ExecutionPolicy Bypass -File scripts/init-env.ps1

config:
	docker compose config --quiet

build:
	docker compose build control-api dispatcher worker

up:
	docker compose up -d --build

dashboard:
	powershell -ExecutionPolicy Bypass -File scripts/open-dashboard.ps1 -SideEffectsTest

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

creator-outreach-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/creator-outreach-smoke.ps1

recovery-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/recovery-smoke.ps1

lifecycle-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/lifecycle-smoke.ps1

agent-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/agent-smoke.ps1

openrouter:
	powershell -ExecutionPolicy Bypass -File scripts/openrouter.ps1 -Smoke

backup:
	powershell -ExecutionPolicy Bypass -File scripts/backup.ps1

restore-drill:
	powershell -ExecutionPolicy Bypass -File scripts/restore-drill.ps1

readiness:
	powershell -ExecutionPolicy Bypass -File scripts/readiness.ps1

vps-init:
	bash scripts/vps-init-env.sh

vps-preflight:
	bash scripts/vps-preflight.sh

vps-up:
	bash scripts/vps-up.sh

vps-smoke:
	bash scripts/vps-smoke.sh

vps-local-model:
	bash scripts/vps-local-model.sh --smoke

vps-model-health:
	bash scripts/vps-model-health.sh

vps-dashboard-login:
	bash scripts/vps-dashboard-login.sh

vps-install-service:
	bash scripts/vps-install-service.sh

vps-backup:
	bash scripts/vps-backup.sh

vps-restore-drill:
	bash scripts/vps-restore-drill.sh

clean:
	docker compose down --remove-orphans
