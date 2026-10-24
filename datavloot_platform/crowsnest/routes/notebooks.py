"""
Notebooks route — discovers and launches Marimo notebooks from the project's notebooks/ directory.
"""

import atexit
import pathlib
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datavloot_platform.crowsnest.config import get_config
from datavloot_platform.crowsnest.processes import kill_port as _kill_port
from datavloot_platform.crowsnest.processes import start_marimo

router = APIRouter()

_marimo_process: "subprocess.Popen | None" = None


@router.get("/list")
async def list_notebooks():
    """List all .py notebooks in the project's notebooks/ directory."""
    notebooks_dir = pathlib.Path.cwd() / "notebooks"
    if not notebooks_dir.exists():
        return {"notebooks": [], "available": False}
    notebooks = [
        {"name": f.name, "stem": f.stem}
        for f in sorted(notebooks_dir.glob("*.py"))
        if f.is_file()
    ]
    return {"notebooks": notebooks, "available": True}


class LaunchRequest(BaseModel):
    name: str


@router.post("/launch")
async def launch_notebook(req: LaunchRequest):
    """Start a Marimo notebook server for the given notebook file."""
    global _marimo_process

    name = pathlib.Path(req.name).name
    if not name.endswith(".py"):
        raise HTTPException(400, "Only .py files can be launched")

    notebook_path = pathlib.Path.cwd() / "notebooks" / name
    if not notebook_path.exists():
        raise HTTPException(404, f"Notebook '{name}' not found in notebooks/")

    # Marimo runs as its own service (the Falcon): nothing to start, only where to go.
    public_url = get_config().marimo_public_url
    if public_url:
        return {"launched": name, "url": f"{public_url}/?file={name}"}

    # Kill any existing marimo instance before launching a fresh one.
    if _marimo_process is not None:
        try:
            _marimo_process.kill()
        except Exception:
            pass
        _marimo_process = None
    _kill_port(2718)

    _marimo_process = start_marimo(
        ["edit", "--headless", "--no-token", "--port", "2718", str(notebook_path)]
    )
    return {"launched": name, "url": "http://127.0.0.1:2718"}


@router.post("/stop")
async def stop_notebook():
    """Kill the running Marimo server."""
    global _marimo_process
    if get_config().marimo_public_url:
        # Not ours to stop: the Marimo service serves everyone.
        return {"stopped": False}
    if _marimo_process is not None:
        try:
            _marimo_process.kill()
        except Exception:
            pass
        _marimo_process = None
    _kill_port(2718)
    return {"stopped": True}


@atexit.register
def _stop_server() -> None:
    # Started in its own process group, so it would outlive the Crows Nest and
    # go on serving a notebook from a session that is over: the next Crows Nest
    # then shows it as running, even when the file has moved since.
    if _marimo_process is not None and _marimo_process.poll() is None:
        try:
            _marimo_process.kill()
        except Exception:
            pass
