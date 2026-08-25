# Test readiness

## One-command gate

Run from the repository root:

```powershell
./scripts/readiness.ps1
```

The local-model check reuses an installed model so the gate remains useful when
the model registry is temporarily unavailable. On a new machine it downloads
the configured model automatically. To deliberately refresh the model first,
run `./scripts/local-model.ps1 -ForcePull`.

The default gate requires all configured paths:

| Check | Proves |
|---|---|
| Core lifecycle verification | Build, lint, tests, health, approval, retry, cancellation, dead letters |
| Disposable restore drill | Latest authoritative state can be restored and read by application code |
| Agent doctor | Docker/WSL/configuration/core/OmniRoute/Hermes/GPU readiness |
| OmniRoute smoke | Authenticated `free/default` route returns a real completion |
| Local-model smoke | Qwen3 8B returns `LOCAL_MODEL_OK` and Ollama reports GPU placement |
| Hermes one-shot | Hermes returns `HERMES_READY_OK` through its configured route |

The script writes only check names, status, duration, error summary, timestamp,
and Git commit to ignored `runtime/readiness/latest.json`. It does not write
tokens, prompts, provider configuration, database content, or model output.

Skip switches exist for diagnosing an intentionally unconfigured optional path:

```powershell
./scripts/readiness.ps1 -SkipRemoteInference -SkipHermes
```

A skipped check does not prove readiness. The default no-skip run is required
before claiming this workstation's complete configured test stack is ready.

## Safe first manual tests

After the gate passes:

1. Submit a harmless `foundation.echo` task through the API and inspect its
   correlation ID and audit timeline.
2. Submit a high-risk echo simulation, confirm it remains pending, then approve
   it through the decision endpoint.
3. Ask Hermes a read-only question with tools still disabled.
4. Compare the same non-sensitive prompt through `free/default` and local
   `qwen3:8b`; expect different quality and latency.
5. Run `./scripts/side-effect-smoke.ps1`. It uses only a fake ATS and local
   Mailpit sink, yet exercises the real approval and duplicate-guard code.

Do not use purchases, real email, real job submission, public publishing, host
filesystem tools, or destructive operations as first tests. Application/email
adapters exist, but real destinations remain exact-approval-gated and need
destination-specific manual configuration/compatibility checks.
