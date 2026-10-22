"""
Notebooks route — discovers and launches Marimo notebooks from the project's notebooks/ directory.
"""

import os
import pathlib
import socket
import subprocess
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datavloot_platform.crowsnest.config import get_config

router = APIRouter()

MARIMO_PORT = 2718

# The one process the Crows Nest owns: the Marimo it launched itself. Anything
# else on MARIMO_PORT -- typically the user's own Marimo in another project --
# is left alone.
_marimo_process: "subprocess.Popen | None" = None
_marimo_notebook: "str | None" = None


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def stop_marimo() -> bool:
    """Stop the Marimo this Crows Nest started, if any. Returns whether there was one."""
    global _marimo_process, _marimo_notebook
    if _marimo_process is None:
        return False
    try:
        _marimo_process.kill()
        _marimo_process.wait(timeout=10)
    except Exception:
        pass
    _marimo_process = None
    _marimo_notebook = None
    return True


@router.get("/list")
async def list_notebooks():
    """
    List all .py notebooks in the project's notebooks/ directory.

    running is the notebook of the Marimo this Crows Nest started, if it is still
    alive; external is true when Marimo is a service of its own (the Falcon). The
    panel embeds Marimo only in those two cases, never a Marimo that merely
    answers on the port.
    """
    running = _marimo_notebook if _marimo_process is not None and _marimo_process.poll() is None else None
    external = bool(get_config().marimo_public_url)
    notebooks_dir = pathlib.Path.cwd() / "notebooks"
    if not notebooks_dir.exists():
        return {"notebooks": [], "available": False, "running": running, "external": external}
    notebooks = [
        {"name": f.name, "stem": f.stem}
        for f in sorted(notebooks_dir.glob("*.py"))
        if f.is_file()
    ]
    return {"notebooks": notebooks, "available": True, "running": running, "external": external}


class LaunchRequest(BaseModel):
    name: str


@router.post("/launch")
async def launch_notebook(req: LaunchRequest):
    """Start a Marimo notebook server for the given notebook file."""
    global _marimo_process, _marimo_notebook

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

    # Replace our own Marimo; refuse rather than kill one we did not start.
    stop_marimo()
    if _port_in_use(MARIMO_PORT):
        raise HTTPException(
            409,
            f"Port {MARIMO_PORT} is in use by a Marimo the Crows Nest did not start "
            "(another project, or one left over from an earlier session). "
            "Stop it and launch again.",
        )

    # python.exe (not pythonw.exe — that breaks marimo's asyncio kernel).
    # STARTUPINFO with SW_HIDE hides the console window at the Win32 show-window
    # level, which is more reliable for console apps than CREATE_NO_WINDOW alone.
    launcher = sys.executable

    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    _marimo_process = subprocess.Popen(
        [launcher, "-m", "marimo", "edit", "--headless", "--no-token", "--port", str(MARIMO_PORT), str(notebook_path)],
        **kwargs,
    )
    _marimo_notebook = name
    return {"launched": name, "url": f"http://127.0.0.1:{MARIMO_PORT}"}


@router.post("/stop")
async def stop_notebook():
    """Stop the Marimo server the Crows Nest started."""
    if get_config().marimo_public_url:
        # Not ours to stop: the Marimo service serves everyone.
        return {"stopped": False}
    return {"stopped": stop_marimo()}
