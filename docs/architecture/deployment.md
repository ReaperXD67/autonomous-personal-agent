# Deployment model

## Local

Windows → Docker Desktop → Linux containers → single Compose project. Project
dependencies stay in images. Source, Compose, schema, and docs are committed;
`.env` and named volumes stay local.

## CI

CI renders Compose with disposable secrets, builds images, runs repository
contracts and unit tests, and never activates optional credentialed profiles.
Future stages may add SBOM generation, Trivy, Gitleaks, image signing, and
published images after versioning exists.

## KVM VPS

Target remains single-host Compose initially. This is easier to audit and back
up than premature orchestration. Required additions before production:

1. hardened non-root SSH access, firewall, automatic security updates;
2. DNS, TLS reverse proxy, authenticated admin surface, request rate limits;
3. external secret manager or root-readable Docker secrets, including SMTP;
4. encrypted off-host backups plus tested restore drills;
5. monitoring/alerts for health, disk, queue age, task failures, and certificates;
6. pinned release promotion, rollback procedure, and maintenance window;
7. provider, Telegram, email, and GitHub credentials scoped per capability;
8. egress policy and reconciliation procedure for approval-bound side effects.

Kubernetes is intentionally rejected for foundation: one VPS does not justify
its operational cost. Compose boundaries preserve a later migration path.
