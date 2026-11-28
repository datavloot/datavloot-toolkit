"""
The Crows Nest's MCP server on /mcp (#67): read-only tools for an agent.

The tools must refuse what the SQL editor refuses, also where the editor itself may
write, and return what the API returns, nothing more. On a laptop there is no
sign-in, so /mcp must not answer a web page in the user's browser: a request from
another origin, or under a host name that only resolves to 127.0.0.1 (DNS
rebinding), is refused.
"""

import json
import logging
import subprocess
import sys
import threading
import time

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")
pytest.importorskip("mcp", reason="mcp is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest.routes import pipelines  # noqa: E402

LAPTOP = "http://127.0.0.1:8080"
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    import duckdb

    db = tmp_path / "p.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA probe_business")
    con.execute(
        "CREATE TABLE probe_business.dim_vessel AS "
        "SELECT i AS vessel_key, 'v' || i AS name FROM range(50) t(i)"
    )
    con.execute("CREATE SCHEMA probe_elementary")
    con.execute(
        "CREATE TABLE probe_elementary.dbt_models AS SELECT * FROM (VALUES "
        "('model.probe.dim_vessel', 'dim_vessel', 'probe_business', 'p', 'One row per vessel.', "
        "NULL, '[]', 'probe', 'business/dim_vessel.sql'), "
        "('model.probe.dim_port', 'dim_port', 'probe_business', 'p', 'One row per port.', "
        "NULL, '[]', 'probe', 'business/dim_port.sql')"
        ") t(unique_id, alias, schema_name, database_name, description, owner, tags, package_name, path)"
    )
    con.close()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CROWSNEST_DUCKDB_PATH", str(db))
    monkeypatch.setenv("CROWSNEST_ELEMENTARY_SCHEMA", "probe_elementary")
    for name in ("CROWSNEST_AUTH_TOKEN", "CROWSNEST_SQL_WRITE", "CROWSNEST_MCP_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    cn_config.reset_config()
    yield db
    cn_config.reset_config()


def _client(host="127.0.0.1", base_url=LAPTOP):
    from datavloot_platform.crowsnest.server import create_app

    # `with`, so the app's lifespan runs: the MCP server's session manager lives in it.
    return TestClient(create_app(host=host), base_url=base_url)


@pytest.fixture
def client(warehouse):
    with _client() as c:
        yield c


def rpc(client, method, params=None, **headers):
    return client.post(
        "/mcp",
        headers={**HEADERS, **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        follow_redirects=False,
    )


def call(client, tool, **arguments) -> dict:
    response = rpc(client, "tools/call", {"name": tool, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def data(result) -> dict:
    assert not result["isError"], result
    return json.loads(result["content"][0]["text"])


def error(result) -> str:
    assert result["isError"], result
    return result["content"][0]["text"]


def tool_names(client) -> set[str]:
    response = rpc(client, "tools/list")
    assert response.status_code == 200, response.text
    return {tool["name"] for tool in response.json()["result"]["tools"]}


def rows_in_dim_vessel(db) -> int:
    import duckdb

    with duckdb.connect(str(db), read_only=True) as con:
        return con.execute("SELECT count(*) FROM probe_business.dim_vessel").fetchone()[0]


# --------------------------------------------------------------------------
# the tools
# --------------------------------------------------------------------------

def test_the_three_read_tools_are_listed(client):
    assert tool_names(client) == {"query", "catalog", "runs"}


def test_query_returns_columns_and_rows(client):
    result = data(call(client, "query", sql="SELECT vessel_key, name FROM probe_business.dim_vessel ORDER BY 1 LIMIT 2"))
    assert result["columns"] == ["vessel_key", "name"]
    assert result["rows"] == [[0, "v0"], [1, "v1"]]
    assert result["truncated"] is False


def test_query_is_capped(client):
    result = data(call(client, "query", sql="SELECT * FROM range(20000)", limit=50000))
    assert result["row_count"] == 10_000
    assert result["truncated"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO probe_business.dim_vessel VALUES (99, 'x')",
        "DELETE FROM probe_business.dim_vessel",
        "DROP TABLE probe_business.dim_vessel",
        "COPY probe_business.dim_vessel TO 'out.csv'",
        "ATTACH 'other.duckdb'",
        "INSTALL httpfs",
        # #53: runs the statement it explains.
        "EXPLAIN ANALYZE SELECT 1",
        "SELECT 1; DROP TABLE probe_business.dim_vessel",
    ],
)
def test_query_refuses_what_the_editor_refuses(client, warehouse, sql):
    # The statement check's own words, so it was refused before it reached DuckDB.
    message = error(call(client, "query", sql=sql))
    assert "not allowed" in message or "One statement at a time" in message
    assert rows_in_dim_vessel(warehouse) == 50
    assert not (warehouse.parent / "out.csv").exists()


@pytest.mark.parametrize(
    "tool, arguments, target",
    [("query", {"sql": "SELECT 1"}, "run_read"), ("catalog", {}, "get_models")],
)
def test_the_tools_read_on_a_thread_of_their_own(client, monkeypatch, tool, arguments, target):
    # DuckDB blocks: on the event loop it would hold up every other request, and
    # on the default pool a query the agent gave up on would keep a thread that
    # /api/health and Shut down need.
    from datavloot_platform.crowsnest.routes import catalog, query

    module = query if target == "run_read" else catalog
    real = getattr(module, target)
    seen = []

    def spy(*args):
        seen.append(threading.current_thread().name)
        return real(*args)

    monkeypatch.setattr(module, target, spy)
    data(call(client, tool, **arguments))
    assert len(seen) == 1 and seen[0].startswith("crowsnest-mcp"), seen


def test_the_tools_read_one_at_a_time(client, monkeypatch):
    # On a .duckdb file a second read connection fails while the first is open.
    from datavloot_platform.crowsnest.routes import query

    real = query.run_read
    release = threading.Event()
    lock = threading.Lock()
    running, most = [0], [0]

    def slow(*args):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        release.wait(10)
        try:
            return real(*args)
        finally:
            with lock:
                running[0] -= 1

    monkeypatch.setattr(query, "run_read", slow)
    results = []
    calls = [
        threading.Thread(target=lambda: results.append(call(client, "query", sql="SELECT 1")))
        for _ in range(4)
    ]
    for thread in calls:
        thread.start()
    try:
        deadline = time.monotonic() + 5
        while most[0] < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.5)  # time for a second to start, if it could
    finally:
        release.set()
        for thread in calls:
            thread.join(10)
    assert most[0] == 1
    assert [data(result)["rows"] for result in results] == [[[1]]] * 4


def test_query_refuses_writes_where_the_editor_may_write(warehouse, monkeypatch):
    monkeypatch.setenv("CROWSNEST_SQL_WRITE", "1")
    with _client() as c:
        assert c.get("/api/query/mode").json()["write"] is True
        message = error(call(c, "query", sql="DELETE FROM probe_business.dim_vessel"))
    assert "not allowed" in message
    # The editor's advice to set CROWSNEST_SQL_WRITE would send the user the wrong way.
    assert "CROWSNEST_SQL_WRITE" not in message
    assert rows_in_dim_vessel(warehouse) == 50


def test_catalog_returns_what_the_catalog_api_returns(client):
    everything = data(call(client, "catalog"))
    assert everything == client.get("/api/catalog/models").json()
    assert everything["total"] == 2
    found = data(call(client, "catalog", search="vessel"))
    assert found == client.get("/api/catalog/models?search=vessel").json()
    assert [m["name"] for m in found["models"]] == ["dim_vessel"]


def test_catalog_of_one_table_returns_its_detail(client):
    detail = client.get("/api/catalog/models/dim_vessel").json()
    assert data(call(client, "catalog", table="dim_vessel")) == detail
    assert "not found" in error(call(client, "catalog", table="no_such_table"))


def test_runs_returns_what_the_runs_api_returns(client, monkeypatch):
    async def dagster(query, variables=None):
        if "logsForRun" in query:
            return {"data": {"logsForRun": {"events": [{
                "__typename": "ExecutionStepFailureEvent", "stepKey": "dim_vessel",
                "error": {"message": "Binder Error: column x not found", "causes": []},
            }]}}}
        return {"data": {"runsOrError": {"__typename": "Runs", "results": [{
            "runId": "r1", "status": "FAILURE", "jobName": "daily", "assetSelection": None,
            "startTime": 1.0, "endTime": 3.0, "tags": [{"key": "dagster/schedule_name", "value": "daily"}],
        }]}}}

    monkeypatch.setattr(pipelines, "_dagster_query", dagster)
    runs = data(call(client, "runs"))
    assert runs == client.get("/api/pipelines/runs").json()
    assert runs["runs"][0]["error"] == "dim_vessel: Binder Error: column x not found"


def test_runs_says_when_dagster_is_not_there(client, monkeypatch):
    monkeypatch.setenv("CROWSNEST_DAGSTER_URL", "http://127.0.0.1:9/graphql")
    cn_config.reset_config()
    assert "Dagster" in error(call(client, "runs"))


# --------------------------------------------------------------------------
# who may call it
# --------------------------------------------------------------------------

def test_mcp_answers_on_its_path_without_a_redirect(client):
    assert rpc(client, "tools/list").status_code == 200


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:3000", LAPTOP])
def test_a_web_page_cannot_call_it_on_a_laptop(client, origin):
    # Agents send no Origin; a browser always does, also for a page on another
    # local port, and the dashboard itself does not use /mcp.
    assert rpc(client, "tools/list", origin=origin).status_code == 403


def test_a_rebound_host_name_cannot_call_it_on_a_laptop(client):
    # evil.example resolving to 127.0.0.1 makes the attacker's page same-origin;
    # only the Host header gives it away.
    assert rpc(client, "tools/list", host="evil.example:8080").status_code == 421


# Without a port too: a Crows Nest on port 80.
@pytest.mark.parametrize("host", ["localhost:8080", "127.0.0.1:8080", "[::1]:8080", "localhost"])
def test_the_loopback_names_are_accepted(client, host):
    assert rpc(client, "tools/list", host=host).status_code == 200


def test_any_loopback_address_it_listens_on_is_accepted(warehouse):
    # All of 127.0.0.0/8 is loopback (config.is_loopback), and a client sends the
    # address it connected to.
    with _client(host="127.0.0.2", base_url="http://127.0.0.2:8080") as c:
        assert rpc(c, "tools/list").status_code == 200
        assert rpc(c, "tools/list", host="evil.example:8080").status_code == 421


def test_get_is_refused(client):
    # Stateless, nothing needs the event stream a GET opens. A page's no-cors GET
    # sends no Origin, so the checks above would let it hold one open.
    answer = []
    thread = threading.Thread(
        target=lambda: answer.append(client.get("/mcp", headers={"accept": "text/event-stream"})),
        daemon=True,
    )
    thread.start()
    thread.join(5)
    assert answer, "GET /mcp is still open after 5 s"
    assert answer[0].status_code == 405
    assert answer[0].headers["allow"] == "POST"


def test_off_loopback_the_host_name_is_not_checked(warehouse):
    # On a VM or the Falcon the sign-in in front is the boundary, and the app does
    # not know the name it is reached under.
    with _client(host="0.0.0.0", base_url="http://falcon.example.nl") as c:
        assert rpc(c, "tools/list").status_code == 200


def test_the_token_is_required_when_set(warehouse, monkeypatch):
    monkeypatch.setenv("CROWSNEST_AUTH_TOKEN", "s3cret")
    with _client() as c:
        assert rpc(c, "tools/list").status_code == 401
        assert rpc(c, "tools/list", authorization="Bearer s3cret").status_code == 200


# --------------------------------------------------------------------------
# CROWSNEST_MCP_TOOLS and the extra
# --------------------------------------------------------------------------

def test_only_the_listed_tools_are_on(warehouse, monkeypatch):
    monkeypatch.setenv("CROWSNEST_MCP_TOOLS", "catalog, runs")
    with _client() as c:
        assert tool_names(c) == {"catalog", "runs"}
        assert error(call(c, "query", sql="SELECT 1"))


def test_an_empty_list_turns_the_server_off(client, monkeypatch):
    assert rpc(client, "tools/list").status_code == 200
    monkeypatch.setenv("CROWSNEST_MCP_TOOLS", "")
    with _client() as c:
        # The dashboard's static files answer instead, and they take no POST.
        assert rpc(c, "tools/list").status_code == 405


def _start(monkeypatch):
    """`datavloot launch` up to the point where uvicorn would serve."""
    import argparse

    import uvicorn

    from datavloot_platform import cli

    class Server:
        def __init__(self, config):
            pass

        def run(self):
            pass

    monkeypatch.setattr(uvicorn, "Server", Server)
    cli.cmd_crowsnest(argparse.Namespace(host="127.0.0.1", port=8099, open=False))


def test_an_unknown_tool_stops_the_start(warehouse, monkeypatch):
    monkeypatch.setenv("CROWSNEST_MCP_TOOLS", "query,materialize_all")
    with pytest.raises(ValueError, match="materialize_all"):
        _client()
    # From the CLI an error line, as for CROWSNEST_SQL_WRITE, not a traceback.
    with pytest.raises(SystemExit, match="^Error: CROWSNEST_MCP_TOOLS .*materialize_all"):
        _start(monkeypatch)


def test_the_start_says_whether_the_mcp_server_is_on(warehouse, monkeypatch, capsys):
    _start(monkeypatch)
    assert "MCP:     query, catalog, runs on /mcp" in capsys.readouterr().out
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
    _start(monkeypatch)
    assert "MCP:     off (needs the mcp extra)" in capsys.readouterr().out


def test_without_the_extra_there_is_no_mcp_server(client, monkeypatch):
    assert rpc(client, "tools/list").status_code == 200
    # None in sys.modules makes the import fail, as when the package is absent.
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
    with _client() as c:
        assert rpc(c, "tools/list").status_code == 405
        assert c.get("/api/health").status_code == 200


def test_the_crows_nest_imports_without_the_mcp_package(warehouse):
    # A fresh interpreter, so no module imported mcp before it was blocked.
    script = (
        "import sys; sys.modules['mcp'] = None\n"
        "from fastapi.testclient import TestClient\n"
        "from datavloot_platform.crowsnest.server import create_app\n"
        "print(TestClient(create_app(host='127.0.0.1')).get('/api/health').status_code)\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert result.stdout.strip() == "200", result.stderr


def test_it_does_not_rest_on_an_sdk_class_without_docs(warehouse, monkeypatch):
    # StreamableHTTPASGIApp is in no SDK guide; were a 2.x release to move it,
    # the Crows Nest must still start, with its MCP server.
    from mcp.server import streamable_http_manager

    monkeypatch.delattr(streamable_http_manager, "StreamableHTTPASGIApp")
    with _client() as c:
        assert tool_names(c) == {"query", "catalog", "runs"}


def test_the_server_leaves_the_log_level_alone(warehouse, monkeypatch):
    # The SDK calls logging.basicConfig, which acts only while the root logger has
    # no handler: as under uvicorn, not under pytest, which installs its own.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    with _client() as c:
        assert rpc(c, "tools/list").status_code == 200
    # At INFO every request the Crows Nest makes to Dagster would be logged.
    assert root.level == logging.WARNING
