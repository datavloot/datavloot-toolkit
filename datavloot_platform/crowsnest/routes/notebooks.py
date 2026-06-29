"""
Notebooks route — discovers and launches Marimo notebooks from the project's notebooks/ directory.
"""

import pathlib
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


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
    # Strip directory components to prevent path traversal
    name = pathlib.Path(req.name).name
    if not name.endswith(".py"):
        raise HTTPException(400, "Only .py files can be launched")

    notebook_path = pathlib.Path.cwd() / "notebooks" / name
    if not notebook_path.exists():
        raise HTTPException(404, f"Notebook '{name}' not found in notebooks/")

    subprocess.Popen(
        ["marimo", "edit", str(notebook_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"launched": name, "url": "http://localhost:2718"}
