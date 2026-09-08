# ADR-0015 — Managed routing, lazy local inference, and browser sessions

Status: Accepted

Date: 2026-09-08

## Context

Normal Hermes startup required two implementation details that did not match the
operator workflow: Ollama was an opt-in profile even though it was the final
continuity route, and the dashboard expected the long-lived control-plane token
to be copied into browser memory. The private VPS tooling could start Compose,
but did not install a boot-managed service or periodically prove provider
health.

Hermes supports an ordered top-level `fallback_providers` list. OpenRouter also
provides a free-model router. The desired interactive hierarchy is therefore
OmniRoute first, OpenRouter's free router second, and local Qwen last.

## Decision

- Render the committed Hermes configuration into its private data volume with a
  one-shot, networkless configuration container on every agent-profile start.
- Configure the interactive chain as OmniRoute `free/default`, then
  `openrouter/free`, then internal Ollama `qwen3:8b`.
- Start the lightweight Ollama daemon with the agent profile and cache Qwen, but
  do not make an inference request during normal startup. `OLLAMA_KEEP_ALIVE`
  unloads model weights after idle time. `-LocalModel` is an explicit canary and
  unloads the model after it passes unless the operator asks to keep it loaded.
- Keep the career worker's separately governed direct OpenRouter adapter. Its
  exact-`:free` catalog checks, privacy filters, zero-cost attestation, and
  PostgreSQL reservation ledger remain stricter than the general interactive
  route.
- Replace normal token copy/paste with a 90-second, one-use bootstrap carried in
  the URL fragment. The dashboard removes the fragment before API use and
  exchanges it for a signed HttpOnly, SameSite=Strict cookie. Unsafe cookie
  requests require an HMAC-derived CSRF header and exact same-origin validation.
  Bearer authentication remains available for scripts and manual recovery.
- Keep Compose `restart: unless-stopped` for container crash recovery. On a
  private Linux VPS, install a systemd oneshot unit that starts the full Compose
  application after Docker and re-runs the fail-closed startup on failure. A
  persistent systemd timer probes the committed route order and all three model
  endpoints every 15 minutes.
- Continue binding dashboard/admin ports to loopback. The browser cookie remains
  non-Secure only for the documented loopback HTTP connection through an SSH or
  VPN tunnel; a future HTTPS profile must set the Secure attribute.

## Alternatives considered

- Copy the service bearer token on every launch: rejected because it needlessly
  exposes a long-lived machine secret to the clipboard and browser JavaScript.
- Start or stop the Ollama container from Hermes on demand: rejected because it
  would require a Docker socket or similarly privileged host control inside the
  agent boundary. Keeping an empty daemon ready gives lazy model-weight loading
  without granting host control.
- Keep OpenRouter career-only: superseded for interactive Hermes continuity at
  the operator's request. The governed career adapter remains separate because
  it has a different privacy, accounting, and audit contract.
- Depend only on manual VPS commands: rejected because reboot and crash recovery
  are normal production lifecycle requirements.

## Consequences

Normal local use is one command and does not load Qwen or copy a control token.
The VPS can boot and recover without an interactive shell. A configured
OpenRouter credential is now required for the complete production hierarchy,
and the general Hermes route may consume the same account-wide free allowance
outside the career ledger. Diagnostics report this composition instead of
claiming quota isolation. Ollama itself consumes a small amount of idle memory;
the much larger Qwen weights and GPU allocation remain lazy.

This decision supersedes ADR-0013 only where that ADR reserved OpenRouter
exclusively for career drafting and made Hermes fall back directly to Qwen. Its
deterministic discovery, career prioritization, and governed drafting decisions
remain in force. It extends ADR-0014 with an installed service lifecycle and a
safer private-browser login.
