import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.settings import settings


class DapiError(RuntimeError):
    pass


class DiffusionClient:
    """Drives a Diffusion Studio editor instance via the `dapi` CLI.

    Replaces the original Playwright/`window.core` integration: the editor
    open-sourced its automation surface as a project folder of JSX plus the
    `dapi` CLI (open/context/check/capture/export talking to a running app
    over a local socket) rather than a headless-browser `window.core` global
    (grep of the whole editor-fork git history found no trace of
    `window.core` ever existing there -- it targeted a different, no-longer-
    reachable hosted build). This client writes the composition as JSX to
    the project's entry file and shells out to `dapi` for everything else.
    """

    def __init__(
        self,
        project_dir: Optional[str] = None,
        cli_path: Optional[str] = None,
        entry_file: str = "index.tsx",
    ):
        self.project_dir = Path(project_dir or settings.dapi_project_dir).resolve()
        self.cli_path = cli_path or settings.dapi_cli_path
        self.entry_file = entry_file
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self._opened = False

    # -- low level -----------------------------------------------------

    def _run(self, args: list[str], timeout: int = 90) -> str:
        cmd = ["node", self.cli_path, *args]
        logger.debug(f"dapi: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise DapiError(
                f"dapi {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip()

    def _run_json(self, args: list[str], timeout: int = 90) -> Any:
        out = self._run(args, timeout=timeout)
        lines = [line for line in out.splitlines() if line.strip()]
        if not lines:
            return None
        if len(lines) == 1:
            return json.loads(lines[0])
        return [json.loads(line) for line in lines]

    # -- lifecycle -------------------------------------------------------

    def ensure_open(self) -> dict:
        """Opens (or creates) the project folder in the running app.

        The app itself must already be running (headless, under Xvfb on
        Linux -- `dapi open` only auto-launches the app on macOS); the
        service that owns this client is responsible for keeping that
        process alive.
        """
        result = self._run_json(["open", "-b", str(self.project_dir)])
        self._opened = True
        logger.info(f"dapi open: {result}")
        return result

    def upload_assets(self, assets: list[str]) -> None:
        """No-op placeholder kept for tool-call compatibility.

        Assets are referenced directly by absolute path in JSX `src` props
        (see editor-fork/reference/jsx/media.md -- "Global path" resolution),
        so there is no separate upload step against a browser file input.
        """
        return None

    # -- composition -----------------------------------------------------

    def write_project(self, jsx: str) -> None:
        """Writes the project's entry file. The app watches the folder and
        recompiles + remounts on save (see reference/jsx/README.md pipeline)."""
        if not self._opened:
            self.ensure_open()
        path = self.project_dir / self.entry_file
        path.write_text(jsx)
        logger.debug(f"Wrote {len(jsx)} bytes to {path}")
        # Give the app's file watcher + esbuild compile a moment to land
        # before a caller immediately calls context/check/capture.
        time.sleep(1.5)

    def context(self) -> dict:
        return self._run_json(["context"])

    def check(self, node_id: str) -> dict:
        return self._run_json(["check", node_id])

    def capture(
        self, scene_id: str, times: Optional[list[str]] = None, output_dir: Optional[str] = None
    ) -> list[dict]:
        """Renders frames of a scene to contact-sheet PNG(s) and returns
        their paths. Mirrors what an export would encode at each position."""
        out_dir = Path(output_dir or (self.project_dir / ".captures"))
        out_dir.mkdir(parents=True, exist_ok=True)
        args = ["capture", scene_id, "-o", str(out_dir)]
        if times:
            args += ["-t", *times]
        result = self._run_json(args, timeout=120)
        if isinstance(result, dict):
            result = [result]
        return result or []

    def export(self, scene_id: str, output: str) -> dict:
        """Encodes a scene to a video file on disk. Waits for the CLI's own
        render loop rather than polling (the CLI blocks until it's done,
        up to its own 60-minute ceiling)."""
        out_path = Path(output)
        if not out_path.is_absolute():
            out_path = self.project_dir / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = self._run_json(["export", scene_id, str(out_path)], timeout=3600)
        logger.info(f"dapi export: {result}")
        return result

    def close(self) -> None:
        """The app process is a shared, long-lived host service (one
        browser/editor session per host, per the WO's v1 scope) -- this
        client does not own its lifecycle and does not stop it."""
        return None
