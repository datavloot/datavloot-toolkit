"""
The Marimo servers the Crows Nest starts on a laptop: one for notebooks
(routes/notebooks.py) and one for apps (routes/apps.py). Behind a proxy (the
Falcon) both are services of their own and nothing here runs. The CLI stops
`dagster dev` the same way the Crows Nest stops these.
"""

import os
import signal
import subprocess
import sys


def terminate_tree(proc: subprocess.Popen) -> None:
    """
    Kill the whole process tree, not just the launcher.

    `dagster dev` supervises a webserver, a daemon, and gRPC code-server children.
    proc.terminate() signals only the launcher, orphaning the grandchildren -- they
    keep holding port 3000 and spawning dbt runs after datavloot has exited, so every
    failed start leaves debris that interferes with the next one.
    """
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # taskkill walks the tree itself: /T includes children, /F forces.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def kill_port(port: int) -> None:
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


def start_marimo(args: list[str]) -> subprocess.Popen:
    """
    Start `python -m marimo <args>` in the background, without a console window.

    python.exe (not pythonw.exe — that breaks marimo's asyncio kernel).
    STARTUPINFO with SW_HIDE hides the console window at the Win32 show-window
    level, which is more reliable for console apps than CREATE_NO_WINDOW alone.
    """
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

    return subprocess.Popen([sys.executable, "-m", "marimo", *args], **kwargs)
