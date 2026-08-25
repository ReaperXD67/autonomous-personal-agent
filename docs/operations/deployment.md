# VPS deployment strategy

Foundation is locally validated, not production-approved. Use a dedicated KVM
VPS after the following gate is complete.

## Host baseline

- supported Linux LTS, automatic security patches, NTP, encrypted disk where available;
- unprivileged deploy user, SSH keys, password login disabled, root login disabled;
- firewall allows SSH from trusted addresses and HTTPS only;
- Docker Engine from official repository with log rotation and resource limits;
- repository checkout at a fixed release tag, not a mutable branch.

## Secrets

Replace `.env` with Docker secrets or an external secret manager where upstream
images support file-based secrets. If `.env` remains temporarily, restrict it to
root/deploy user, exclude it from backups unless backup encryption is verified,
and rotate after suspected exposure.

## Ingress

For the first private deployment, keep the command-center and OmniRoute ports on
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

Keep the `side-effects-test` profile local only. A VPS that will execute reviewed
external actions uses `side-effects`, an egress firewall/proxy where available,
and deployment-managed SMTP secrets. Run the local fixture smoke before enabling
real destinations. Never mount a workstation browser profile or publish Mailpit.
Treat an `ambiguous` action as an incident to reconcile with the destination;
do not retry it by hand until the external state is known.

## Still missing for production

Central monitoring, automated encrypted off-host backups, rate limiting/OIDC on
the control API, TLS proxy configuration, secrets-manager integration, signed
release images, and incident runbooks. Migrations and owned worker leases are
implemented, but production rollback and restore policy still need rehearsal on
the chosen VPS.
