#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
deploy_user="$(id -un)"
deploy_group="$(id -gn)"
docker_path="$(command -v docker || true)"
unit_path='/etc/systemd/system/hermes.service'
health_service_path='/etc/systemd/system/hermes-model-health.service'
health_timer_path='/etc/systemd/system/hermes-model-health.timer'

if [[ "$(uname -s)" != 'Linux' || "$(id -u)" -eq 0 ]]; then
  printf '%s\n' 'Run this on Linux as the dedicated non-root deploy user.' >&2
  exit 1
fi
if [[ -z "$docker_path" ]] || ! command -v systemctl >/dev/null 2>&1 ||
    ! command -v sudo >/dev/null 2>&1; then
  printf '%s\n' 'docker, systemctl, and sudo are required.' >&2
  exit 1
fi
if [[ "$project_root" =~ [[:space:]] || "$deploy_user" =~ [^A-Za-z0-9_.-] || "$deploy_group" =~ [^A-Za-z0-9_.-] ]]; then
  printf '%s\n' 'The project path must contain no whitespace and the user/group must be systemd-safe.' >&2
  exit 1
fi

cd "$project_root"
"$script_dir/vps-preflight.sh"
for managed_path in "$unit_path" "$health_service_path" "$health_timer_path"; do
  if sudo test -f "$managed_path" &&
      ! sudo grep -q '^# Managed by Hermes vps-install-service.sh$' "$managed_path"; then
    printf 'Refusing to replace an existing unmanaged unit: %s\n' "$managed_path" >&2
    exit 1
  fi
done

temporary_unit="$(mktemp)"
temporary_health_service="$(mktemp)"
temporary_health_timer="$(mktemp)"
cleanup() {
  rm -f -- "$temporary_unit" "$temporary_health_service" "$temporary_health_timer"
}
trap cleanup EXIT
cat >"$temporary_unit" <<EOF
# Managed by Hermes vps-install-service.sh
[Unit]
Description=Hermes private single-operator stack
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$deploy_user
Group=$deploy_group
WorkingDirectory=$project_root
ExecStart=$project_root/scripts/vps-up.sh --no-build
ExecReload=$project_root/scripts/vps-up.sh --no-build
ExecStop=$docker_path compose --project-directory $project_root --profile agent --profile side-effects stop
TimeoutStartSec=900
TimeoutStopSec=180
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
cat >"$temporary_health_service" <<EOF
# Managed by Hermes vps-install-service.sh
[Unit]
Description=Hermes model-provider health probe
After=hermes.service
Requires=hermes.service

[Service]
Type=oneshot
User=$deploy_user
Group=$deploy_group
WorkingDirectory=$project_root
ExecStart=$project_root/scripts/vps-model-health.sh
TimeoutStartSec=120
EOF
cat >"$temporary_health_timer" <<'EOF'
# Managed by Hermes vps-install-service.sh
[Unit]
Description=Run the Hermes model-provider health probe periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true
Unit=hermes-model-health.service

[Install]
WantedBy=timers.target
EOF
chmod 600 "$temporary_unit" "$temporary_health_service" "$temporary_health_timer"
sudo install -m 0644 "$temporary_unit" "$unit_path"
sudo install -m 0644 "$temporary_health_service" "$health_service_path"
sudo install -m 0644 "$temporary_health_timer" "$health_timer_path"
sudo systemctl daemon-reload
sudo systemctl enable --now hermes.service
sudo systemctl enable --now hermes-model-health.timer
sudo systemctl --no-pager --full status hermes.service
sudo systemctl --no-pager --full status hermes-model-health.timer
printf '%s\n' 'HERMES_SERVICE_OK: boot startup, crash recovery, and provider-health timer are enabled.'
