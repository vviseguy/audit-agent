"""Host-side wrapper around `docker run agents:latest`.

The scheduler calls `dispatch_run(run_id)` for each session it fires. This
builds the docker command, streams stdout/stderr into a log file, and
returns the exit code. One container per run; no shared state beyond the
mounted volumes.

On platforms where Docker is unavailable (dev laptops without Docker
Desktop) the caller can opt into `in_process=True`, which runs the job
in the current Python process. This is convenient for smoke tests but
loses the sandbox.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE = os.environ.get("AGENTS_IMAGE", "agents:latest")
NETWORK = os.environ.get("AGENTS_NETWORK", "anthropic-only")


@dataclass
class DispatchResult:
    run_id: int
    exit_code: int
    log_path: str
    mode: str  # 'docker' | 'in_process'


def _volumes_from_config(cfg: dict) -> list[str]:
    # Map host paths -> in-container mount points. The host paths are read
    # from config.yaml; the container paths are fixed in Dockerfile.agents.
    paths = cfg.get("paths", {})
    db_host = str(Path(paths["db"]).parent.resolve())
    clones_host = str(Path(paths["clones"]).resolve())
    chroma_host = str(Path(paths["chroma"]).resolve())
    return [
        f"{db_host}:/db",
        f"{clones_host}:/clones",
        f"{chroma_host}:/chroma",
    ]


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def dispatch_run(
    run_id: int,
    *,
    cfg: dict,
    log_dir: Path,
    in_process: bool = False,
) -> DispatchResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{run_id}.log"

    if in_process or not _docker_available():
        log.warning(
            "dispatching run %d in-process (docker available: %s)",
            run_id,
            _docker_available(),
        )
        from orchestrator.run_job import main as run_main

        argv_backup = sys.argv
        sys.argv = ["run_job", str(run_id)]
        try:
            with open(log_path, "w", encoding="utf-8") as fh:
                stdout_backup = sys.stdout
                stderr_backup = sys.stderr
                sys.stdout = fh
                sys.stderr = fh
                try:
                    code = run_main()
                finally:
                    sys.stdout = stdout_backup
                    sys.stderr = stderr_backup
        finally:
            sys.argv = argv_backup
        return DispatchResult(run_id=run_id, exit_code=int(code or 0),
                              log_path=str(log_path), mode="in_process")

    env_passthrough = [
        "ANTHROPIC_API_KEY",
        "GITHUB_PAT_READ",
        "GITHUB_PAT_ISSUES",
    ]
    env_args: list[str] = []
    for name in env_passthrough:
        if os.environ.get(name):
            env_args += ["-e", name]

    volume_args: list[str] = []
    for v in _volumes_from_config(cfg):
        volume_args += ["-v", v]

    cmd = (
        [
            "docker", "run", "--rm",
            f"--network={NETWORK}",
            "--read-only",
            "--tmpfs", "/tmp",
        ]
        + env_args
        + volume_args
        + [IMAGE, "orchestrator.run_job", str(run_id)]
    )
    log.info("dispatch run %d: %s", run_id, " ".join(cmd))
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    return DispatchResult(
        run_id=run_id,
        exit_code=proc.returncode,
        log_path=str(log_path),
        mode="docker",
    )
