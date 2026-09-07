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
./scripts/vps-backup.sh
./scripts/vps-restore-drill.sh
```

`vps-init-env.sh` refuses to overwrite an existing `.env`, generates the core
secrets without printing them, selects production mode, and restricts Host
headers to loopback. `vps-preflight.sh` refuses placeholders, broad secret-file
permissions, a dirty checkout, Mailpit, non-loopback published ports, host
networking, privileged containers, and Docker-socket mounts. Warnings identify
the host/account checks that cannot be proven from the repository.

`vps-up.sh` builds and starts core services, waits for database/Redis readiness,
then creates one harmless safe task and one separately approved harmless task.
It prints task IDs but never the bearer token. Use optional flags deliberately:

```bash
./scripts/vps-up.sh --side-effects   # only after complete TLS SMTP setup
./scripts/vps-up.sh --agent          # only after OmniRoute onboarding
./scripts/vps-up.sh --local-model    # only on an NVIDIA-enabled VPS
```

From the workstation, open the private dashboard through a tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 deploy@YOUR_VPS
```

Then browse to `http://127.0.0.1:8080`. Keep the bootstrap token in page memory
only and clear the clipboard after pasting it.

## Secrets

Replace `.env` with Docker secrets or an external secret manager where upstream
images support file-based secrets. If `.env` remains temporarily, restrict it to
root/deploy user, exclude it from backups unless backup encryption is verified,
and rotate after suspected exposure.

Treat the OpenRouter inference key as worker-only and use a normal scoped key
with a provider-side spend limit/expiry, never a management key. A CPU-only VPS
also needs either this hosted route or enough resources for its local fallback;
free hosted capacity is not an uptime guarantee.

## Ingress

For the first private deployment, keep command-center and OmniRoute ports on
loopback and use WireGuard/Tailscale or SSH tunnels. Do not publish upstream
admin dashboards. Public HTTPS requires OIDC/RBAC in front of the command
center, rate limits, body-size limits, secure headers, request timeouts, and TLS.
The single bootstrap bearer token is insufficient for public internet exposure.

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
