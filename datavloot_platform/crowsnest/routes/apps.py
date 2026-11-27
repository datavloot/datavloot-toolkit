"""
Apps route — the project's dashboards: Marimo notebooks in the apps/ directory,
served with `marimo run`, so they show their output and not their code.

notebooks/ is where the crew explores (`marimo edit`, routes/notebooks.py);
apps/ is what they hand over to people who look at results. On a laptop one
`marimo run apps` server serves every app, started on first use and kept
running, so switching between apps does not restart anything; opening an app
added since it started restarts it, as it reads the directory only once. Behind a proxy
(the Falcon) the apps are a service of their own and the Crows Nest only links
to it, as it does for Marimo.
"""

import asyncio
import atexit
import pathlib
import re
import subprocess
import threading
import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datavloot_platform.crowsnest.config import get_config
from datavloot_platform.crowsnest.httpclient import async_client
from datavloot_platform.crowsnest.processes import port_in_use, port_taken_message, start_marimo, stop_process

router = APIRouter()

APPS_DIR = "apps"

# How long a cold `marimo run` may take before the open request gives up.
_START_TIMEOUT_SECONDS = 30

_apps_process: "subprocess.Popen | None" = None
# Held for the check and the start only, not for the wait until the server
# answers, so a second Open is not held up by the first.
_start_lock = threading.Lock()
# The apps the running server found when it started. `marimo run apps` reads the
# directory once, so a file added later answers 404 until the server restarts.
_served: "set[str]" = set()
# Why the last restart failed, for an Open that was waiting on the server it replaced.
_restart_failure: "str | None" = None

_APP_TITLE = re.compile(r"""app_title\s*=\s*(["'])(.+?)\1""")


def _title(path: pathlib.Path) -> str:
    """The app's app_title from its marimo.App(...) call, else its file name."""
    try:
        match = _APP_TITLE.search(path.read_text(encoding="utf-8"))
    except OSError:
        match = None
    return match.group(2) if match else path.stem


@router.get("/list")
async def list_apps():
    """List the .py apps in the project's apps/ directory."""
    apps_dir = pathlib.Path.cwd() / APPS_DIR
    if not apps_dir.is_dir():
        return {"apps": [], "available": False}
    apps = [
        {"name": f.name, "title": _title(f)}
        for f in sorted(apps_dir.glob("*.py"))
        if f.is_file()
    ]
    return {"apps": apps, "available": True}


class OpenRequest(BaseModel):
    name: str


@router.post("/open")
async def open_app(req: OpenRequest):
    """Where the browser finds the given app; starts the apps server when needed."""
    name = pathlib.Path(req.name).name
    if not name.endswith(".py"):
        raise HTTPException(400, "Only .py files can be opened")
    if not (pathlib.Path.cwd() / APPS_DIR / name).is_file():
        raise HTTPException(404, f"App '{name}' not found in {APPS_DIR}/")

    config = get_config()
    # The apps run as their own service (the Falcon): nothing to start.
    if config.apps_public_url:
        return {"name": name, "url": f"{config.apps_public_url}/?file={name}"}

    # Where we start it, as for notebooks: always 127.0.0.1, on the port of the URL.
    url = f"http://127.0.0.1:{config.apps_port}"
    await _ensure_server(url, name)
    return {"name": name, "url": f"{url}/?file={name}"}


async def _ensure_server(url: str, name: str) -> None:
    """Start `marimo run apps` unless ours is running and knows `name`, and wait until it answers."""
    process = await asyncio.to_thread(_start_unless_running, name)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _START_TIMEOUT_SECONDS
    async with async_client(2.0) as client:
        while loop.time() < deadline:
            if process.poll() is not None:
                # A restart for another Open stops this process on purpose; the lock
                # is free when the new one is in place.
                current = await asyncio.to_thread(_current_process)
                if current is not process:
                    process = current
                    continue
                if _restart_failure:
                    raise HTTPException(
                        500, f"Restarting the apps server for another dashboard failed: {_restart_failure}"
                    )
                raise HTTPException(
                    500,
                    f"`marimo run {APPS_DIR}` stopped right after starting; run it in a terminal "
                    "in the project directory to see why.",
                )
            try:
                if (await client.get(url)).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise HTTPException(504, f"The apps server did not answer at {url} within {_START_TIMEOUT_SECONDS}s.")


def _current_process() -> "subprocess.Popen":
    with _start_lock:
        return _apps_process


def _start_unless_running(name: str) -> "subprocess.Popen":
    global _restart_failure
    with _start_lock:
        try:
            process = _start_locked(name)
        except Exception as error:
            _restart_failure = str(getattr(error, "detail", error))
            raise
        _restart_failure = None
        return process


def _start_locked(name: str) -> "subprocess.Popen":
    global _apps_process
    # The port of CROWSNEST_APPS_URL, so the check and the wait look where we start.
    port = get_config().apps_port

    running = _apps_process is not None and _apps_process.poll() is None
    if running and name in _served:
        return _apps_process
    if running:
        # A dashboard added since the server started: only a restart loads it.
        stop_process(_apps_process)
        # On Windows the port can still answer for a moment after the tree is
        # gone; wait, or the restart would take our own server for a stranger's.
        deadline = time.monotonic() + 5
        while port_in_use(port) and time.monotonic() < deadline:
            time.sleep(0.1)
    # Whatever else holds the port (another project's apps, or a server left
    # from an earlier session) is not ours to stop.
    if port_in_use(port):
        raise HTTPException(409, port_taken_message(port))
    _served.clear()
    _served.update(f.name for f in (pathlib.Path.cwd() / APPS_DIR).glob("*.py"))
    _apps_process = start_marimo(
        ["run", APPS_DIR, "--headless", "--no-token", "--port", str(port)]
    )
    return _apps_process


@atexit.register
def _stop_server() -> None:
    # Started in its own process group, so it would outlive the Crows Nest and
    # keep serving this project's apps after `datavloot start` is stopped.
    stop_process(_apps_process)
