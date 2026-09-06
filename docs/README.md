# vidzs-composer — service one-pager

CADIS-routed smolagents agent that drives the Diffusion Studio editor (`dapi` CLI) to compose and export videos from natural-language instructions.

## HTTP service (FastAPI, port 3341)

- `POST /compose` `{ instruction, assets: [abs paths], project_dir? }` → `202 {"job_id"}`
- `GET /compose/{job_id}` → `{ status: queued|running|done|error, result?, output? }`

Jobs run sequentially on one background worker thread against a single shared DiffusionClient/editor session (v1 scope — no concurrent jobs).

## Environment variable NAMES (values live in Infisical/secret store — never commit)

| Var | Default | Purpose |
|---|---|---|
| `CADIS_GATEWAY_URL` | `https://cadis.geniuzs.com/v1` | CADIS gateway base for LiteLLM |
| `VIDEO_COMPOSER_MODEL` | `cadis` | model id, sent to LiteLLM as `openai/$VIDEO_COMPOSER_MODEL` |
| `EMBEDDING_PROVIDER` | `cloudflare` | docs-search embeddings (CF bge-m3 via CADIS `/v1/embeddings`) |
| `DAPI_CLI_PATH` | repo `apps/cli/dist/index.js` (bin `dapi`) | editor automation CLI |
| `DAPI_PROJECT_DIR` | project workspace dir | JSX project the agent drives |

## CADIS routing

`main.py` builds the LiteLLM client with `model_id=f"openai/{settings.video_composer_model}"` and `api_base=settings.cadis_gateway_url`. LiteLLM logs to `logs/litellm_calls.log` (`LiteLLM-Success` lines confirm routing). Cost-map warnings for `cadis` are benign.

## Caller contract (DEVVY / vidzs worker)

- Callers (vidzs worker `web/src/devvy.ts`, DEVVY beats, or any host process) POST natural-language `instruction`s to `POST /compose`.
- The agent translates instruction → project JSX → `dapi` ops → export; polling `GET /compose/{job_id}` yields the output path under `output/`.
- Docs search (RAG over the fork's JSX/docs corpus in Qdrant, collection `diffusion_studio_docs`) backs the agent's tool calls; content-hash keyed, re-embeds only on corpus change.

## Reused vs added (fork lineage)

Reused: RoseBludd/agent fork (smolagents CodeAgent, tools, prompts, docs corpus), RoseBludd/editor fork `dapi` CLI + Electron app. Added: CADIS LiteLLM routing (`main.py`), env surface (`src/settings.py`), `dapi`-based `src/client.py`, HTTP `service.py`, `g3_test.py`.
