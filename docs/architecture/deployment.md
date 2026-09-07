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

## Private KVM VPS

Target remains single-host Compose initially. This is easier to audit and back
up than premature orchestration. The prepared private profile generates
owner-only secrets, requires `APP_ENV=production`, validates Host headers,
refuses dirty checkouts/test mail/public port bindings/privileged boundaries,
starts the stack, and proves both safe and approval-gated work. It is reached
only through an SSH or VPN tunnel.

The deployable private-alpha gate still requires operator-owned host setup:

1. hardened non-root SSH access, firewall, automatic security updates;
2. exact release tag or reviewed commit plus rollback window;
3. encrypted off-host copies of checksummed dumps and a tested restore drill;
4. monitoring/alerts for health, disk, queue age, and task failures;
5. capability-scoped provider credentials and external-action reconciliation.

Public production remains a later boundary and additionally needs TLS, OIDC/RBAC,
rate limits/body limits, step-up approval identity, centralized secrets, and
signed release images. A reverse proxy must not be used to make the current
bootstrap-token dashboard public.

Kubernetes is intentionally rejected for foundation: one VPS does not justify
its operational cost. Compose boundaries preserve a later migration path.
