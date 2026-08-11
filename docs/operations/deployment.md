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

Expose one HTTPS reverse proxy. Do not publish OmniRoute/Hermes admin dashboards
publicly; access through WireGuard or SSH tunnels. Add authentication, rate
limits, body-size limits, secure headers, and request timeouts. Set OmniRoute
secure-cookie mode only after HTTPS exists.

## Promotion

1. Back up and verify free disk.
2. Pull reviewed release tag and inspect diff.
3. Render `docker compose config`; run image/security scans.
4. Pull/build images and verify their digests.
5. Run migrations/boot during maintenance window.
6. Check health, smoke task, logs, queue age, and external provider canary.
7. Roll back images/config if gate fails; restore data only when migration is incompatible.

## Still missing for production

Central monitoring, automated encrypted backups, schema migration runner,
worker leases, rate limiting on control API, TLS proxy configuration, secrets
manager integration, and incident runbooks.

