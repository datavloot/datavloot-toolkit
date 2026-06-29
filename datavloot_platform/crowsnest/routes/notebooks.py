"""
Notebooks route — discovers and launches Marimo notebooks from the project's notebooks/ directory.
"""

import os
import pathlib
import subprocess
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_marimo_process: "subprocess.Popen | None" = None


def _kill_port(port: int) -> None:
    """Kill whatever process is currently listening on port."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                    pid = parts[4]
                    if pid.isdigit() and int(pid) > 0:
                        subprocess.run(
                            ["taskkill", "/PID", pid, "/F"],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
        else:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            for pid in result.stdout.strip().splitlines():
                if pid.isdigit():
                    subprocess.run(["kill", "-9", pid], capture_output=True)
    except Exception:
        pass


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

    # Kill any existing marimo instance before launching a fresh one.
    if _marimo_process is not None:
        try:
            _marimo_process.kill()
        except Exception:
            pass
        _marimo_process = None
    _kill_port(2718)

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
        [launcher, "-m", "marimo", "edit", "--headless", "--no-token", "--port", "2718", str(notebook_path)],
        **kwargs,
    )
    return {"launched": name, "url": "http://127.0.0.1:2718"}


@router.post("/stop")
async def stop_notebook():
    """Kill the running Marimo server."""
    global _marimo_process
    if _marimo_process is not None:
        try:
            _marimo_process.kill()
        except Exception:
            pass
        _marimo_process = None
    _kill_port(2718)
    return {"stopped": True}
