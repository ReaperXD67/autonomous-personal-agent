# VPS deployment strategy

The repository is locally validated and now includes a fail-closed private VPS
runbook. It is suitable for a single operator only after the selected host
passes the commands below. It is not approved for direct public exposure.

## Host baseline

- supported 64-bit Linux LTS, automatic security patches, NTP, encrypted disk where available;
- unprivileged deploy user, SSH keys, password login disabled, root login disabled;
- firewall/provider security group allows SSH from trusted addresses only;
- [Docker Engine and Compose from the official repository](https://docs.docker.com/engine/install/ubuntu/)
  with log rotation and resource limits;
- repository checkout at an exact reviewed commit or fixed release tag, not an
  unreviewed mutable branch.

Docker warns that [published container ports interact directly with its firewall
rules](https://docs.docker.com/engine/network/packet-filtering-firewalls/) and
can bypass assumptions made in UFW/firewalld policy.
Hermes therefore keeps every declared host port on `127.0.0.1`; the preflight
also verifies the rendered Compose model. Do not add a public port mapping.

## First private deployment

Run as the dedicated deploy user from a clean exact checkout:

```bash
./scripts/vps-init-env.sh
chmod 600 .env
# Edit .env only for capability-scoped provider credentials you intend to use.
./scripts/vps-preflight.sh
./scripts/vps-up.sh
./scripts/vps-install-service.sh
./scripts/vps-backup.sh
./scripts/vps-restore-drill.sh
```

`vps-init-env.sh` refuses to overwrite an existing `.env`, generates the core
secrets without printing them, selects production mode, and restricts Host
headers to loopback. `vps-preflight.sh` refuses placeholders, broad secret-file
permissions, a dirty checkout, Mailpit, non-loopback published ports, host
networking, privileged containers, and Docker-socket mounts. Warnings identify
the host/account checks that cannot be proven from the repository.

`vps-up.sh` builds and starts the core services plus the complete managed model
hierarchy, waits for readiness, creates one harmless safe task and one
separately approved harmless task, and performs non-generating provider health
checks. A new host whose OmniRoute administrator has not been onboarded uses
the bootstrap mode first:

```bash
./scripts/vps-up.sh --bootstrap-omniroute
# Complete loopback-only OmniRoute onboarding and add both scoped provider keys.
./scripts/vps-up.sh
./scripts/vps-up.sh --local-model    # optional explicit Qwen canary; CPU or NVIDIA
```

Normal startup does not need `--agent` or `--local-model`. The former is kept as
a compatibility no-op; the latter deliberately loads Qwen once, checks the
exact response and GPU placement when applicable, then unloads it. The Ollama
daemon remains supervised so Hermes can reach it without Docker-socket access,
while Qwen weights load only on demand and expire after the configured idle
period. Set `VPS_SIDE_EFFECTS_ENABLED=true` only after complete TLS SMTP setup.

After the first full deployment passes, `vps-install-service.sh` installs and
enables `hermes.service` plus a persistent 15-minute
`hermes-model-health.timer`. Compose restart policies recover individual
containers; systemd starts the project after Docker on reboot and retries a
failed startup. Inspect them with:

```bash
systemctl status hermes.service hermes-model-health.timer
journalctl -u hermes.service -u hermes-model-health.service
docker compose --profile agent logs --tail=200 hermes omniroute ollama
```

From the workstation, open the private dashboard through a tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 deploy@YOUR_VPS
```

In another VPS shell, run `./scripts/vps-dashboard-login.sh` and open its URL
within 90 seconds. The one-use fragment is removed from browser history and
exchanged for an HttpOnly session. The service bearer token is not printed,
copied, or stored by the page.

## Secrets

Replace `.env` with Docker secrets or an external secret manager where upstream
images support file-based secrets. If `.env` remains temporarily, restrict it to
root/deploy user, exclude it from backups unless backup encryption is verified,
and rotate after suspected exposure.

Treat the OpenRouter value as an inference-only secret used by Hermes and the
career worker; use a provider-side spend limit/expiry, never a management key.
General Hermes fallback calls do not participate in the career worker's local
reservation ledger. A CPU-only VPS can run Qwen as a last resort, but it may be
slow; free hosted capacity is not an uptime guarantee.

## Ingress

For the first private deployment, keep command-center and OmniRoute ports on
loopback and use WireGuard/Tailscale or SSH tunnels. Do not publish upstream
admin dashboards. Public HTTPS requires OIDC/RBAC in front of the command
center, rate limits, body-size limits, secure headers, request timeouts, and TLS.
The private signed browser session is insufficient for public internet exposure.

## Promotion

1. Back up and verify free disk.
2. Pull reviewed release tag and inspect diff.
3. Render `docker compose config`; run image/security scans.
4. Pull/build images and verify their digests.
5. Run migrations/boot during maintenance window.
6. Check health, smoke task, logs, queue age, and external provider canary.
7. Roll back images/config if gate fails; restore data only when migration is incompatible.

Keep the `side-effects-test` profile off the VPS. A VPS that will execute reviewed
external actions uses `side-effects`, an egress firewall/proxy where available,
and deployment-managed SMTP secrets. Run the local fixture smoke before enabling
real destinations. Never mount a workstation browser profile or publish Mailpit.
Treat an `ambiguous` action as an incident to reconcile with the destination;
do not retry it by hand until the external state is known.

## Still missing for public/multi-user production

Central monitoring, automated encrypted off-host backups, rate limiting/OIDC on
the control API, TLS proxy configuration, secrets-manager integration, signed
release images, and incident runbooks. Migrations and owned worker leases are
implemented; `vps-backup.sh` and `vps-restore-drill.sh` prove mechanics, but
encryption, transfer, scheduling, retention, alerts, and rollback still need
rehearsal on the chosen VPS.
