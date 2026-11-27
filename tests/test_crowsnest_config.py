"""
Which warehouse the Crows Nest serves, and when it finds out.

The project's lake appears with the first write: on a fresh Falcon the
Crows Nest starts with the stack and the first pipeline run comes later. It
has to find the lake then, without a restart (#93).
"""

import os

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform import storage  # noqa: E402
from datavloot_platform.crowsnest import config as cn_config  # noqa: E402


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project without a lake yet, as the current directory, with nothing configured."""
    for var in [v for v in os.environ if v.startswith("CROWSNEST_")]:
        monkeypatch.delenv(var)
    monkeypatch.delenv(storage.LAKE_DIR_ENV, raising=False)
    root = tmp_path / "sales"
    root.mkdir()
    (root / "dbt_project.yml").write_text("name: 'sales'\nversion: '1.0.0'\n", encoding="utf-8")
    monkeypatch.chdir(root)
    cn_config.reset_config()
    yield root
    cn_config.reset_config()


def make_client() -> TestClient:
    from datavloot_platform.crowsnest.server import create_app
    return TestClient(create_app())


def write_lake(project) -> None:
    """What the first pipeline run leaves behind: a lake with a table in it."""
    conn = storage.connect(project)
    conn.execute("CREATE SCHEMA sales_business")
    conn.execute("CREATE TABLE sales_business.dim_customer AS SELECT range AS customer_key FROM range(3)")
    conn.close()


def duckdb_health(client: TestClient) -> str:
    return client.get("/api/health").json()["services"]["duckdb"]


def test_a_lake_created_after_the_start_is_found_without_a_restart(project):
    client = make_client()
    assert duckdb_health(client) == "offline"

    write_lake(project)

    assert duckdb_health(client) == "ok"
    r = client.post("/api/query/execute", json={"sql": "SELECT * FROM sales_business.dim_customer"})
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 3
    # Found once, kept: not looked for again on every request.
    assert cn_config.get_config() is cn_config.get_config()



@pytest.mark.parametrize(
    "marimo_url, apps_url, ports",
    [
        (None, None, (2718, 2719)),
        ("http://127.0.0.1:2801", "http://127.0.0.1:2800/", (2801, 2800)),
        ("http://marimo:2900", "http://apps", (2900, 2719)),
    ],
)
def test_the_marimo_servers_take_their_port_from_the_url(project, monkeypatch, marimo_url, apps_url, ports):
    for var, url in (("CROWSNEST_MARIMO_URL", marimo_url), ("CROWSNEST_APPS_URL", apps_url)):
        if url:
            monkeypatch.setenv(var, url)
    cn_config.reset_config()

    config = cn_config.get_config()

    assert (config.marimo_port, config.apps_port) == ports
