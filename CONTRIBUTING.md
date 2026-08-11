# Contributing

This project values small, reviewable changes that preserve security boundaries.

1. Open an issue for new external integrations or privilege expansion.
2. Create a focused branch from `main`.
3. Update tests, docs, threat model, and engineering journal where behavior changes.
4. Run `./scripts/test.ps1`, `docker compose config --quiet`, and relevant smoke tests.
5. Never include credentials, private data, browser profiles, or rendered config.

Changes that add tool access must document source, image/version, credential
scope, read/write behavior, risk class, approval rule, safe validation, and
disable path.

