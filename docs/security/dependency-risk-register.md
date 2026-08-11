# Dependency risk register

Last reviewed: 2026-08-11

This register records an explicit, reviewable exception. It is not permission to
ignore future advisories.

## Current package state

Direct Python dependencies are pinned to the versions in
`services/control-api/uv.lock`. The August 2026 update moves FastAPI to `0.141.1`,
pytest to `9.1.1`, and the remaining direct runtime/dev packages to their tested
current versions. This resolves the pytest temporary-directory advisory.

FastAPI `0.141.1` still resolves Starlette `0.47.3`. Six Starlette advisories have
patched releases outside FastAPI's currently compatible range. The affected
interfaces are absent from this control plane:

| Advisory | Affected interface | Current exposure |
|---|---|---|
| `GHSA-82w8-qh3p-5jfq` | form-urlencoded parsing via `request.form()` | Not used; API accepts typed JSON bodies |
| `GHSA-jp82-jpqv-5vv3` | `request.url.hostname` authority parsing | Not used for authorization, routing, or policy |
| `GHSA-wqp7-x3pw-xc5r` | Windows UNC paths in `StaticFiles` | No `StaticFiles`; runtime is Linux |
| `GHSA-x746-7m8f-x49c` | method dispatch in `HTTPEndpoint` | No `HTTPEndpoint`; FastAPI routes only |
| `GHSA-86qp-5c8j-p5mr` | Host/path poisoning through `request.url` | Path is structured-log metadata only; never a security decision |
| `GHSA-7f5h-v6xp-fcq8` | Range merging in `FileResponse` | No file-serving route or `FileResponse` |

Repository contract tests fail if these interfaces enter application source.
The API also remains loopback-only, authenticates every non-health route, and is
not approved for public-internet deployment.

## Disposition

Risk classification: accepted as **not used**, with compensating tests. GitHub
alerts may be dismissed only with this register linked in the audit comment.
Reopen the review immediately if application code adds form parsing, static/file
serving, `HTTPEndpoint`, or `request.url`-derived policy. Logging the request path
does not authorize or route work.

Remove this exception as soon as an official FastAPI release supports a patched
Starlette line and the full local/CI smoke suite passes. Dependabot checks weekly.
