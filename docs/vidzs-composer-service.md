# vidzs-composer service (fork lane)

CADIS-routed video composer specialist. Fork of `agent` — the smolagents
agent in `main.py` is wrapped by a FastAPI job service in `service.py`.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/compose` | `{instruction, assets: [abs paths], project_dir?}` | `202 {job_id}` |
| GET | `/compose/{job_id}` | — | job status/result |

Jobs run sequentially on one background worker thread against a single
shared editor session (v1 scope: no concurrent jobs).

## Environment variables (names only — values live in env/Infisical, never in docs)

- `CADIS_GATEWAY_URL` — gateway base URL the agent routes through (default in code: `https://cadis.geniuzs.com/v1`)
- `VIDEO_COMPOSER_MODEL` — model id for the composer agent (default: `cadis`)
- `EMBEDDING_PROVIDER` — embedding backend used by docs search (default: `cloudflare`)

## CADIS routing

All model calls go through the CADIS gateway (`src/settings.py`). The
service never pins a provider key; routing is resolved at runtime from
the env vars above. See `main.py` for the agent/`DiffusionClient` wiring.

## How DEVVY / the vidzs worker calls it

1. `POST /compose` with the beat instruction and absolute asset paths.
2. Poll `GET /compose/{job_id}` until the job reports a terminal status.
3. Treat the returned result as the beat output; the job map is in-process
   (restart loses queued jobs) — resubmit on restart (v1 idempotency scope).
