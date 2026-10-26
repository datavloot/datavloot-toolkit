"""
The Marimo the Notebooks panel starts on a laptop (routes/notebooks.py).

The Crows Nest stops only the Marimo it launched itself, with everything that
Marimo started; any other Marimo on the port is left alone -- typically the
user's own session in another project -- and Launch refuses rather than kill it.
"""

import os
import socket
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

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
