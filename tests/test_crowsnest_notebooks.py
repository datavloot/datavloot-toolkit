"""
The Marimo the Notebooks panel starts on a laptop.

The Crows Nest owns exactly one process: the Marimo it launched itself. It
stops that one when the server shuts down, and it leaves any other Marimo on
the port alone -- typically the user's own session in another project.
"""

import socket
import subprocess
import sys

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest.routes import notebooks  # noqa: E402


_Popen = subprocess.Popen  # the tests patch subprocess.Popen itself


def _sleeper(*args, **kwargs) -> subprocess.Popen:
    """Stands in for Marimo: a real child process, so killing it is real too."""
    return _Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


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

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        monkeypatch.setattr(notebooks, "MARIMO_PORT", s.getsockname()[1])
    monkeypatch.setattr(notebooks, "_marimo_process", None)

    from datavloot_platform.crowsnest.server import create_app
    return create_app()


@pytest.fixture
def foreign_marimo():
    """Something the Crows Nest did not start, listening on the Marimo port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", notebooks.MARIMO_PORT))
        s.listen()
        yield s


def test_shutdown_stops_the_marimo_it_started(app, monkeypatch):
    started = []
    monkeypatch.setattr(notebooks.subprocess, "Popen", lambda *a, **k: started.append(_sleeper()) or started[-1])

    with TestClient(app) as client:
        assert client.post("/api/notebooks/launch", json={"name": "explore.py"}).status_code == 200
        assert started[0].poll() is None

    try:
        started[0].wait(timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail("Marimo outlived the Crows Nest")
    finally:
        started[0].kill()


def test_relaunch_replaces_its_own_marimo(app, monkeypatch):
    started = []
    monkeypatch.setattr(notebooks.subprocess, "Popen", lambda *a, **k: started.append(_sleeper()) or started[-1])

    with TestClient(app) as client:
        client.post("/api/notebooks/launch", json={"name": "explore.py"})
        client.post("/api/notebooks/launch", json={"name": "explore.py"})
        try:
            assert started[0].poll() is not None
            assert started[1].poll() is None
        finally:
            for proc in started:
                proc.kill()


def test_launch_leaves_a_foreign_marimo_alone(app, monkeypatch, foreign_marimo):
    started = []
    monkeypatch.setattr(notebooks.subprocess, "Popen", lambda *a, **k: started.append(a))
    monkeypatch.setattr(notebooks.subprocess, "run", lambda *a, **k: started.append(a))

    with TestClient(app) as client:
        response = client.post("/api/notebooks/launch", json={"name": "explore.py"})

    assert response.status_code == 409
    assert str(notebooks.MARIMO_PORT) in response.json()["detail"]
    assert started == [], "the Crows Nest started or killed a process next to a Marimo it does not own"


def test_stop_leaves_a_foreign_marimo_alone(app, monkeypatch, foreign_marimo):
    killed = []
    monkeypatch.setattr(notebooks.subprocess, "run", lambda *a, **k: killed.append(a))

    with TestClient(app) as client:
        assert client.post("/api/notebooks/stop").json() == {"stopped": False}

    assert killed == []
