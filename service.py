"""HTTP service wrapping the video composer agent.

POST /compose  {instruction, assets: [abs paths], project_dir?}  -> 202 {job_id}
GET  /compose/{job_id}                                            -> status/result

Runs the agent sequentially on a single background worker thread against one
shared DiffusionClient / editor session (v1 scope per the work order: one
browser/editor session is fine, jobs do not run concurrently).
"""

import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from main import agent, client

app = FastAPI(title="vidzs-composer")

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
job_queue: "queue.Queue[str]" = queue.Queue()


class ComposeRequest(BaseModel):
    instruction: str
    assets: list[str] = []
    project_dir: Optional[str] = None


def _set_status(job_id: str, **fields: Any) -> None:
    with jobs_lock:
        jobs[job_id].update(fields)


def _worker() -> None:
    while True:
        job_id = job_queue.get()
        req = jobs[job_id]["request"]
        try:
            _set_status(job_id, status="planning")

            project_dir = req.get("project_dir")
            if project_dir and Path(project_dir).resolve() != client.project_dir:
                client.project_dir = Path(project_dir).resolve()
                client.project_dir.mkdir(parents=True, exist_ok=True)
                client._opened = False

            instruction = req["instruction"]
            assets = req.get("assets") or []
            if assets:
                instruction += "\n\nAvailable assets (absolute paths):\n" + "\n".join(assets)

            _set_status(job_id, status="running")
            result = agent.run(instruction)

            _set_status(
                job_id,
                status="done",
                result=result if isinstance(result, (str, dict, list, type(None))) else str(result),
            )
        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            _set_status(job_id, status="failed", error=str(e))


_worker_thread = threading.Thread(target=_worker, daemon=True)
_worker_thread.start()


@app.post("/compose", status_code=202)
def compose(req: ComposeRequest) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "request": req.model_dump(),
            "status": "queued",
            "result": None,
            "error": None,
        }
    job_queue.put(job_id)
    return {"job_id": job_id}


@app.get("/compose/{job_id}")
def get_compose(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, **job}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
