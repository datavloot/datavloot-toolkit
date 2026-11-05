"""
The Crows Nest opens before Dagster is ready (`datavloot start`), and says so.

From a shortcut nothing showed for half a minute while Dagster loaded the
project; now the Crows Nest is there within seconds and calls Dagster
"starting" until it answers, or "failed" with the reason.
"""

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest import startup  # noqa: E402
from datavloot_platform.crowsnest.server import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    import duckdb

    db = tmp_path / "p.duckdb"
    duckdb.connect(str(db)).close()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CROWSNEST_DUCKDB_PATH", str(db))
    # Nothing listens here: Dagster does not answer.
    monkeypatch.setenv("CROWSNEST_DAGSTER_URL", "http://127.0.0.1:9/graphql")
    monkeypatch.setenv("CROWSNEST_MARIMO_URL", "http://127.0.0.1:9")
    monkeypatch.delenv("CROWSNEST_AUTH_TOKEN", raising=False)
    cn_config.reset_config()
    yield TestClient(create_app(host="127.0.0.1"))
    startup.set_dagster(None)
    cn_config.reset_config()


def test_without_start_a_silent_dagster_is_offline(client):
    """`datavloot launch` on its own sets nothing: the probe decides, as before."""
    startup.set_dagster(None)
    health = client.get("/api/health").json()
    assert health["services"]["dagster"] == "offline"
    assert "dagster_error" not in health


def test_while_dagster_loads_it_is_starting(client):
    startup.set_dagster("starting")
    assert client.get("/api/health").json()["services"]["dagster"] == "starting"


def test_when_loading_failed_it_says_why(client):
    startup.set_dagster("failed", "Code location 'ketenconnect' failed to load: boom")
    health = client.get("/api/health").json()
    assert health["services"]["dagster"] == "failed"
    assert "boom" in health["dagster_error"]


def test_ready_means_the_probe_decides_again(client):
    """Once ready, a Dagster that stops answering is offline, not still starting."""
    startup.set_dagster("ready")
    assert client.get("/api/health").json()["services"]["dagster"] == "offline"
