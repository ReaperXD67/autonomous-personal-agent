# OmniRoute integration boundary

Compose profile `agent` runs official Docker Hub image
`diegosouzapw/omniroute:3.8.49`, pinned by multi-platform digest. Dashboard is
bound to `127.0.0.1` only. State uses named volume `omniroute_data`; Redis uses
database 1 while foundation task queues use database 0.

Bootstrap password and cryptographic secrets come from ignored `.env`.
Inference API-key enforcement is enabled. First boot requires dashboard
onboarding at `http://127.0.0.1:20128`; credentials are never committed.

Upstream source: <https://github.com/diegosouzapw/OmniRoute/releases/tag/v3.8.49>

