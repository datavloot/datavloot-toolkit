"""
The Marimo the Notebooks panel starts on a laptop (routes/notebooks.py).

The Crows Nest stops only the Marimo it launched itself, with everything that
Marimo started; any other Marimo on the port is left alone -- typically the
user's own session in another project -- and Launch refuses rather than kill it.
"""

import argparse
import errno
import io
import os
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform import cli  # noqa: E402
from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest import processes  # noqa: E402
from datavloot_platform.crowsnest.routes import notebooks  # noqa: E402

# Listens on the port it is given until killed: a Marimo, as far as the port can tell.
SERVE = (
    "import socket, sys, time; s = socket.socket(); s.bind(('127.0.0.1', int(sys.argv[1]))); "
    "s.listen(); time.sleep(60)"
)
# Serves the port from a child process, the way Marimo does: behind the venv
# launcher on Windows, and from a kernel process per notebook session.
SERVES_FROM_A_CHILD = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", sys.argv[2], sys.argv[1]])
print(child.pid, flush=True)
time.sleep(60)
"""
# The process group (Windows) or session (POSIX) of its own that start_marimo gives Marimo.
OWN_GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}


def wait_until(condition, timeout=10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


def serves(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def finds_the_listener(port: int) -> str:
    """
    How a 409 must find what holds the port: only the listener, since a browser
    tab still connected to the port must not be the one that gets stopped.
    """
    return f"Get-NetTCPConnection -LocalPort {port} -State Listen" if os.name == "nt" else f"lsof -ti tcp:{port} -sTCP:LISTEN"


def kill_tree(pid: int) -> None:
    """Cleanup for a process and whatever it started, whether or not the test stopped it."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(pid, 9)
        except OSError:
            pass


@pytest.fixture
def app(tmp_path, monkeypatch):
    import duckdb

    db = tmp_path / "p.duckdb"
    duckdb.connect(str(db)).close()
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "notebooks" / "explore.py").write_text("import marimo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CROWSNEST_DUCKDB_PATH", str(db))
    for var in ("CROWSNEST_AUTH_TOKEN", "CROWSNEST_DAGSTER_PUBLIC_URL", "CROWSNEST_MARIMO_PUBLIC_URL"):
        monkeypatch.delenv(var, raising=False)
    cn_config.reset_config()

    # A free port of its own, so a Marimo the developer runs on 2718 is not in the way.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        monkeypatch.setattr(notebooks, "MARIMO_PORT", s.getsockname()[1], raising=False)
    monkeypatch.setattr(notebooks, "_marimo_process", None)
    monkeypatch.setattr(notebooks, "_marimo_notebook", None, raising=False)

    from datavloot_platform.crowsnest.server import create_app
    yield create_app()
    cn_config.reset_config()


@pytest.fixture
def started(monkeypatch):
    """Every stand-in for Marimo the Crows Nest starts; whatever is left of them goes at teardown."""
    procs: list[subprocess.Popen] = []
    yield procs
    for proc in procs:
        kill_tree(proc.pid)
        proc.wait(timeout=10)
        if proc.stdout:
            proc.stdout.close()


def starts_sleepers(monkeypatch, started):
    """start_marimo, with a real process in a group of its own in place of Marimo, so stopping it is real too."""
    def start(args):
        started.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **OWN_GROUP))
        return started[-1]

    monkeypatch.setattr(notebooks, "start_marimo", start)


def starts_servers_with_a_child(monkeypatch, started):
    """start_marimo, with a stand-in that serves the Marimo port from a child process."""
    def start(args):
        started.append(subprocess.Popen(
            [sys.executable, "-c", SERVES_FROM_A_CHILD, str(notebooks.MARIMO_PORT), SERVE],
            stdout=subprocess.PIPE, **OWN_GROUP,
        ))
        return started[-1]

    monkeypatch.setattr(notebooks, "start_marimo", start)


@pytest.fixture
def foreign_marimo(app):
    """Something the Crows Nest did not start, listening on the Marimo port: a process of its own."""
    proc = subprocess.Popen([sys.executable, "-c", SERVE, str(notebooks.MARIMO_PORT)], **OWN_GROUP)
    try:
        assert wait_until(lambda: serves(notebooks.MARIMO_PORT)), "the foreign Marimo never listened"
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_relaunch_replaces_its_own_marimo(app, monkeypatch, started):
    starts_sleepers(monkeypatch, started)
    client = TestClient(app)

    client.post("/api/notebooks/launch", json={"name": "explore.py"})
    client.post("/api/notebooks/launch", json={"name": "explore.py"})

    assert started[0].poll() is not None, "the first Marimo still runs next to the second"
    assert started[1].poll() is None


class SlowToReleaseMarimo:
    """
    Holds the Marimo port until shortly after it is stopped.

    On Windows the port can still answer for a moment after the whole tree is
    gone (1 relaunch in 20 with a real Marimo found it taken). A relaunch in
    that moment must not take our own Marimo for a stranger's.
    """

    def __init__(self, port):
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", port))
        self._sock.listen()
        self._stopped = False

    def poll(self):
        return 0 if self._stopped else None

    def stop(self):
        self._stopped = True
        threading.Timer(0.5, self._sock.close).start()


def test_relaunch_waits_for_its_own_marimo_to_release_the_port(app, monkeypatch):
    started = []

    def start(args):
        started.append(SlowToReleaseMarimo(notebooks.MARIMO_PORT))
        return started[-1]

    monkeypatch.setattr(notebooks, "start_marimo", start)
    monkeypatch.setattr(processes, "terminate_tree", lambda proc: proc.stop())
    client = TestClient(app)

    try:
        assert client.post("/api/notebooks/launch", json={"name": "explore.py"}).status_code == 200
        relaunch = client.post("/api/notebooks/launch", json={"name": "explore.py"})
        assert relaunch.status_code == 200, relaunch.json()
    finally:
        for proc in started:
            proc.stop()


def test_launch_leaves_a_foreign_marimo_alone(app, monkeypatch, started, foreign_marimo):
    starts_sleepers(monkeypatch, started)

    response = TestClient(app).post("/api/notebooks/launch", json={"name": "explore.py"})

    assert response.status_code == 409
    assert finds_the_listener(notebooks.MARIMO_PORT) in response.json()["detail"], (
        "the refusal does not say how to stop it, or would stop its clients too"
    )
    assert started == [], "the Crows Nest started a Marimo next to one it does not own"
    assert foreign_marimo.poll() is None, "the Crows Nest stopped a Marimo it did not start"


def test_stop_leaves_a_foreign_marimo_alone(app, foreign_marimo):
    assert TestClient(app).post("/api/notebooks/stop").json() == {"stopped": False}
    assert foreign_marimo.poll() is None, "the Crows Nest stopped a Marimo it did not start"


def test_stop_after_its_marimo_died_says_so_without_waiting(app, monkeypatch, started):
    """Our Marimo crashed and another took the port: there is nothing of ours to stop or wait for."""
    starts_sleepers(monkeypatch, started)
    client = TestClient(app)

    client.post("/api/notebooks/launch", json={"name": "explore.py"})
    started[0].kill()
    started[0].wait(timeout=10)
    foreign = subprocess.Popen([sys.executable, "-c", SERVE, str(notebooks.MARIMO_PORT)], **OWN_GROUP)
    try:
        assert wait_until(lambda: serves(notebooks.MARIMO_PORT)), "the foreign Marimo never listened"
        begin = time.monotonic()
        stopped = client.post("/api/notebooks/stop").json()
        took = time.monotonic() - begin
        assert foreign.poll() is None, "the Crows Nest stopped a Marimo it did not start"
    finally:
        foreign.kill()
        foreign.wait(timeout=10)

    assert stopped == {"stopped": False}, "reported stopping a Marimo that had already exited"
    assert took < 2, f"/stop blocked the server for {took:.1f}s waiting on a port it does not own"


def test_stop_takes_down_the_whole_process_tree(app, monkeypatch, started):
    starts_servers_with_a_child(monkeypatch, started)
    client = TestClient(app)

    client.post("/api/notebooks/launch", json={"name": "explore.py"})
    child = int(started[0].stdout.readline())
    try:
        assert wait_until(lambda: serves(notebooks.MARIMO_PORT)), "the stand-in never served"
        assert client.post("/api/notebooks/stop").json() == {"stopped": True}
        assert started[0].poll() is not None, "our Marimo itself is still running"
        assert wait_until(lambda: not serves(notebooks.MARIMO_PORT), timeout=5), "a child of our Marimo still serves the port"
    finally:
        kill_tree(child)


def test_list_reports_the_notebook_it_started(app, monkeypatch, started):
    """The panel embeds Marimo only when it is ours, so it has to be told which one that is."""
    starts_sleepers(monkeypatch, started)
    client = TestClient(app)

    assert client.get("/api/notebooks/list").json()["running"] is None
    client.post("/api/notebooks/launch", json={"name": "explore.py"})
    assert client.get("/api/notebooks/list").json()["running"] == "explore.py"
    started[0].kill()
    started[0].wait(timeout=10)
    assert client.get("/api/notebooks/list").json()["running"] is None, "a dead Marimo reported as running"


# `datavloot launch` with a stand-in for the Marimo it started: a process in a
# session of its own, as start_marimo gives it, whose pid goes to stdout.
LAUNCH_WITH_A_MARIMO = """
import argparse, signal, subprocess, sys
if sys.argv[2] == "nohup":
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
from datavloot_platform import cli
from datavloot_platform.crowsnest.routes import notebooks
notebooks._marimo_process = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
)
print(notebooks._marimo_process.pid, flush=True)
cli.cmd_crowsnest(argparse.Namespace(host="127.0.0.1", port=int(sys.argv[1]), open=False))
"""


def running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def launch_with_a_marimo(how=""):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    crowsnest = subprocess.Popen(
        [sys.executable, "-c", LAUNCH_WITH_A_MARIMO, str(port), how],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    marimo = int(crowsnest.stdout.readline())
    assert wait_until(lambda: serves(port), timeout=30), "the Crows Nest never served"
    return crowsnest, marimo


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="Windows has no SIGHUP")
@pytest.mark.parametrize("sig", ["SIGHUP", "SIGTERM"], ids=["terminal closed", "terminated"])
def test_the_marimo_stops_when_the_crows_nest_is_signalled(app, sig):
    """
    Closing the terminal sends SIGHUP, which uvicorn leaves alone. uvicorn shuts
    down on SIGTERM, but then raises it again, and Python's default for both
    ends the process without the atexit hooks that stop Marimo; Marimo, in a
    session of its own, would keep its port.
    """
    crowsnest, marimo = launch_with_a_marimo()
    try:
        crowsnest.send_signal(getattr(signal, sig))
        crowsnest.wait(timeout=30)
        assert wait_until(lambda: not running(marimo), timeout=10), f"Marimo outlived the Crows Nest on {sig}"
    finally:
        crowsnest.kill()
        crowsnest.wait(timeout=10)
        crowsnest.stdout.close()
        kill_tree(marimo)


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="Windows has no SIGHUP")
def test_nohup_still_keeps_the_crows_nest_running(app):
    crowsnest, marimo = launch_with_a_marimo("nohup")
    try:
        crowsnest.send_signal(signal.SIGHUP)
        time.sleep(1)
        assert crowsnest.poll() is None, "the Crows Nest ended on a SIGHUP that nohup told it to ignore"
    finally:
        crowsnest.send_signal(signal.SIGINT)
        crowsnest.wait(timeout=30)
        crowsnest.stdout.close()
        kill_tree(marimo)


class ClosedTerminal(io.StringIO):
    def write(self, text):
        raise OSError(errno.EIO, "Input/output error")


def test_dagster_stops_when_the_terminal_is_gone(app, monkeypatch):
    """
    `dagster dev` runs in a session of its own, so only cmd_start can stop it. By
    then a closed terminal has taken stdout with it, and printing fails.
    """
    dagster = object()
    stopped = []

    def terminal_closes(args):
        monkeypatch.setattr(sys, "stdout", ClosedTerminal())
        sys.exit(0)

    monkeypatch.setattr(cli.subprocess, "Popen", lambda *args, **kwargs: dagster)
    monkeypatch.setattr(cli, "_wait_for_dagster", lambda *args: None)
    monkeypatch.setattr(cli, "cmd_crowsnest", terminal_closes)
    monkeypatch.setattr(cli, "terminate_tree", stopped.append)

    with pytest.raises(SystemExit):
        cli.cmd_start(argparse.Namespace())

    assert stopped == [dagster], "Dagster outlived the closed terminal"


# `datavloot start` up to the Crows Nest, without waiting for a Dagster that will not answer.
START_WITHOUT_WAITING = """
import argparse, sys
from datavloot_platform import cli
cli._wait_for_dagster = lambda *args: None
cli.cmd_start(argparse.Namespace(host="127.0.0.1", port=int(sys.argv[1]), open=False))
"""


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="Windows has no SIGHUP")
def test_dagster_stops_when_a_real_terminal_closes(app, tmp_path, monkeypatch):
    """The whole way, from the SIGHUP on: `dagster dev` here is a script that records its pid and sleeps."""
    import pty

    pid_file = tmp_path / "dagster.pid"
    dagster = tmp_path / "dagster"
    dagster.write_text(f'#!/bin/sh\necho $$ > "{pid_file}"\nexec sleep 60\n', encoding="utf-8")
    dagster.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    start, terminal = pty.fork()
    if start == 0:
        os.execv(sys.executable, [sys.executable, "-c", START_WITHOUT_WAITING, str(port)])
    try:
        assert wait_until(lambda: serves(port), timeout=30), "the Crows Nest never served"
        os.close(terminal)
        assert wait_until(lambda: os.waitpid(start, os.WNOHANG)[0] == start, timeout=30), "datavloot start did not end"
        assert wait_until(lambda: not running(int(pid_file.read_text())), timeout=10), "Dagster outlived the closed terminal"
    finally:
        kill_tree(start)
        if pid_file.exists():
            kill_tree(int(pid_file.read_text()))
