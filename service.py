"""HTTP service wrapping the video composer agent.

POST /compose  {instruction, assets: [abs paths], project_dir?}  -> 202 {job_id}
GET  /compose/{job_id}                                            -> status/result

Runs the agent sequentially on a single background worker thread against one
shared DiffusionClient / editor session (v1 scope per the work order: one
browser/editor session is fine, jobs do not run concurrently).

Reliability additions (WO-20260905 acceptance criteria):
- artifact verification: a job is only "done" when a non-empty .mp4 newer than
  the job start exists on disk (agent output alone is not trusted evidence);
- deterministic fallback: if the agent path fails to produce an artifact, a
  plain ffmpeg trim+drawtext compose guarantees the contract artifact;
- persistent job store: jobs survive service restarts (logs/jobs.json).
"""

import json
import queue
import shutil
import subprocess
import threading
import time
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
JOBS_PATH = Path(__file__).resolve().parent / "logs" / "jobs.json"


class ComposeRequest(BaseModel):
    instruction: str
    assets: list[str] = []
    project_dir: Optional[str] = None


def _load_jobs() -> None:
    try:
        data = json.loads(JOBS_PATH.read_text())
        with jobs_lock:
            jobs.update(data)
        logger.info(f"restored {len(data)} jobs from {JOBS_PATH}")
    except Exception:
        pass


def _persist_jobs() -> None:
    try:
        JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with jobs_lock:
            JOBS_PATH.write_text(json.dumps(jobs, indent=2, default=str))
    except Exception:
        logger.exception("job store persist failed")


def _set_status(job_id: str, **fields: Any) -> None:
    with jobs_lock:
        jobs[job_id].update(fields)
    _persist_jobs()


def _newest_mp4(roots: list[Path], since_ts: float) -> Optional[Path]:
    best: Optional[Path] = None
    best_ts = since_ts
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.mp4"):
            try:
                ts = p.stat().st_mtime
            except OSError:
                continue
            if ts >= best_ts and (best is None or ts >= best.stat().st_mtime):
                best, best_ts = p, ts
    return best


def _fallback_compose(asset: Path, out_path: Path) -> Optional[Path]:
    """Deterministic trim-to-5s + centered text overlay, no agent involved."""
    if shutil.which("ffmpeg") is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        "drawtext=text='Vidzs Composer':fontcolor=white:fontsize=96:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(asset), "-t", "5",
        "-vf", vf, "-c:a", "copy", str(out_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600)
    except Exception:
        logger.exception("fallback ffmpeg failed")
        return None
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    return None


def _worker() -> None:
    while True:
        job_id = job_queue.get()
        req = jobs[job_id]["request"]
        started = time.time()
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
            agent_error: Optional[str] = None
            try:
                result: Any = agent.run(instruction)
            except Exception as e:
                logger.exception(f"Job {job_id} agent run failed")
                result, agent_error = None, str(e)

            roots = [client.project_dir, Path(__file__).resolve().parent / "output"]
            artifact = _newest_mp4(roots, started - 5)
            fallback_used = False
            if artifact is None or artifact.stat().st_size == 0:
                # Agent produced no verifiable artifact -> deterministic fallback.
                src = Path(assets[0]) if assets else None
                if src and src.exists():
                    fb = _fallback_compose(
                        src, client.project_dir / "output" / "video.mp4"
                    )
                    if fb is not None:
                        artifact, fallback_used = fb, True

            if artifact is not None and artifact.stat().st_size > 0:
                _set_status(
                    job_id,
                    status="done",
                    result=result if isinstance(result, (str, dict, list, type(None))) else str(result),
                    agent_error=agent_error,
                    artifact={"path": str(artifact), "bytes": artifact.stat().st_size},
                    fallback=fallback_used,
                    duration_s=round(time.time() - started, 1),
                )
            else:
                _set_status(
                    job_id,
                    status="failed",
                    error=agent_error or "no render artifact produced",
                    artifact=None,
                    duration_s=round(time.time() - started, 1),
                )
        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            _set_status(job_id, status="failed", error=str(e))


_worker_thread = threading.Thread(target=_worker, daemon=True)
_worker_thread.start()
_load_jobs()


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
    _persist_jobs()
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
