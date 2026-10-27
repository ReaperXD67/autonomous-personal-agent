# ADR-0028 — Explicit renewal of an invalid creator Gmail grant

- Date: 2026-10-27
- Status: Accepted
- Extends: ADR-0026 and the shared-mailbox identity guard

## Context

A Testing-mode refresh grant can expire. The existing onboarding helper first
verifies the old account to prevent silently replacing shared career credentials.
An invalid grant cannot establish its old identity, so the safe default also
prevents legitimate renewal of an already recorded creator mailbox.

Treating every refresh failure as expiry would weaken that identity boundary:
wrong clients, outages and malformed responses must not authorize replacement.

## Decision

Add an explicit operator-only `-ReauthorizeExistingMailbox` switch. It requires
all existing OAuth fields, the recorded creator mailbox and label, enabled
creator monitoring, disabled career monitoring, and the same Desktop client
ID/secret. An ordinary setup call retains its previous fail-closed behavior.

Only the refresh request's exact HTTP 400 JSON `invalid_grant` response permits
renewal without verifying the unusable old grant. Provider text is withheld;
the helper propagates a fixed diagnostic marker. Authorization-code failures,
outages, bad clients and malformed responses do not receive that exception.

The new browser consent still passes the existing random state, S256 PKCE,
loopback callback, exact read-only scope, expected mailbox, creator-label and
guarded atomic-save checks. The explicit switch grants no account/client change,
career activation, SMTP sending or broader runtime access. Old settings survive
failed or unfinished consent. No credentials are committed or printed.

## Consequences

An operator can renew the recorded creator connection after a confirmed invalid
grant while preserving shared-career account protection. A changed account or
client still needs a separate explicit resolution. A completed callback and a
fresh governed runtime read are necessary before claiming monitoring recovery;
launching the helper alone proves neither.

Testing-mode longevity and Google's publishing/verification requirements are
unchanged. SMTP remains a separate transport and can succeed while reply reading
is unavailable. Native no-provider regressions cover the narrow renewal exception
and refusals; real consent remains a distinct provider canary.
