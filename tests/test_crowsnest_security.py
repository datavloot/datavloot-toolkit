"""
The Crows Nest query API against hostile input.

Each test names the specific hole it covers. They are written to fail loudly if
someone reinstates first-word filtering or goes back to editing the SQL string to
apply a row cap, because both looked reasonable and both were bypassable.
"""

import pathlib

import pytest

duckdb = pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402


@pytest.fixture(scope="module", params=["file", "lake"])
def client(tmp_path_factory, request) -> TestClient:
    """
    A Crows Nest wired to a small throwaway warehouse: a .duckdb file, or a lake.

    Every test below runs against both. The lake cannot have its file system
    disabled -- DuckLake reads Parquet through it -- so it is sandboxed with
    allowed_directories instead (see db.py), and has to refuse the same attacks.
    """
    import os

    from datavloot_platform import storage

    workdir = tmp_path_factory.mktemp("crowsnest")
    if request.param == "file":
        db = workdir / "probe.duckdb"
        con = duckdb.connect(str(db))
        env = {"CROWSNEST_DUCKDB_PATH": str(db)}
    else:
        lake = workdir / "lake"
        lake.mkdir()
        con = duckdb.connect()
        con.execute(storage.attach_statement(lake / "catalog.sqlite", lake / "data", "probe"))
        con.execute("USE probe")
        # With the prefix, as the variable used to need it: it is accepted and dropped.
        env = {
            "CROWSNEST_DUCKLAKE_CATALOG_PATH": f"ducklake:sqlite:{lake / 'catalog.sqlite'}",
            "CROWSNEST_DUCKLAKE_ALIAS": "probe",
        }
    con.execute("CREATE SCHEMA probe_business")
    con.execute(
        "CREATE TABLE probe_business.dim_vessel AS "
        "SELECT i AS vessel_key, 'v' || i AS name FROM range(50) t(i)"
    )
    con.close()

    os.environ.update(env)
    os.environ.pop("CROWSNEST_AUTH_TOKEN", None)
    cn_config.reset_config()

    from datavloot_platform.crowsnest.server import create_app
    yield TestClient(create_app())

    for name in env:
        os.environ.pop(name, None)
    cn_config.reset_config()


def run(client: TestClient, sql: str, limit: int = 1000):
    return client.post("/api/query/execute", json={"sql": sql, "limit": limit})


# --------------------------------------------------------------------------
# the query still works
# --------------------------------------------------------------------------

def test_a_plain_select_works(client):
    r = run(client, "SELECT vessel_key, name FROM probe_business.dim_vessel ORDER BY 1")
    assert r.status_code == 200, r.text
    assert r.json()["columns"] == ["vessel_key", "name"]
    assert r.json()["row_count"] == 50


@pytest.mark.parametrize("sql", [
    "SHOW TABLES",
    "DESCRIBE SELECT 1 AS x",
    "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
    "EXPLAIN SELECT 1",
    "EXPLAIN SELECT 'analyze' AS x",
])
def test_read_shapes_are_allowed(client, sql):
    """SHOW/DESCRIBE/CTE/EXPLAIN are reads and must not be refused."""
    assert run(client, sql).status_code == 200, sql


# --------------------------------------------------------------------------
# filesystem escape -- read_only does not stop these; the db.py sandbox does
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "COPY (SELECT * FROM probe_business.dim_vessel) TO 'leak.csv'",
    "COPY (SELECT 1) TO 'leak.parquet' (FORMAT PARQUET)",
    "ATTACH 'elsewhere.duckdb' AS other",
    "INSTALL httpfs",
    "LOAD httpfs",
])
def test_filesystem_and_extension_access_is_refused(client, sql):
    r = run(client, sql)
    assert r.status_code in (400, 403), f"{sql!r} returned {r.status_code}: {r.text[:200]}"


def test_explain_analyze_cannot_write_into_the_lake(client, tmp_path):
    """
    EXPLAIN ANALYZE runs the statement it explains and still parses as EXPLAIN.

    On a lake the data directory is writable (see db.py), so this overwrote a live
    Parquet file when pointed at one.
    """
    data = cn_config.get_config().ducklake_data_path
    target = (pathlib.Path(data) if data else tmp_path) / "planted.csv"
    r = run(client, f"EXPLAIN ANALYZE COPY (SELECT 42 AS x) TO '{target.as_posix()}' (FORMAT csv)")
    assert r.status_code in (400, 403), r.text
    assert not target.exists()


@pytest.mark.parametrize("sql", [
    "EXPLAIN ANALYZE SELECT 1",
    "EXPLAIN ANALYSE SELECT 1",
    "EXPLAIN (ANALYZE) SELECT 1",
    "EXPLAIN (FORMAT json, ANALYZE) SELECT 1",
    "EXPLAIN /* a comment */ ANALYZE SELECT 1",
    "explain\nanalyze select 1",
])
def test_explain_analyze_is_refused_however_it_is_spelled(client, sql):
    r = run(client, sql)
    assert r.status_code in (400, 403), f"{sql!r} returned {r.status_code}: {r.text[:200]}"


def test_reading_an_arbitrary_file_is_refused(client, tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a,b\n1,2\n", encoding="utf-8")
    r = run(client, f"SELECT * FROM read_csv('{secret.as_posix()}')")
    assert r.status_code in (400, 403), r.text
    assert "1" not in str(r.json().get("rows", ""))


# --------------------------------------------------------------------------
# statement filtering -- the first-word blocklist walked past all of these
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "INSERT INTO probe_business.dim_vessel VALUES (999, 'x')",
    "-- a leading comment\nDROP TABLE probe_business.dim_vessel",
    "/* block comment */ DELETE FROM probe_business.dim_vessel",
    "  \n\t CREATE TABLE sneaky AS SELECT 1",
    "UPDATE probe_business.dim_vessel SET name = 'x'",
])
def test_writes_are_refused_however_they_are_dressed(client, sql):
    """A leading comment or whitespace used to defeat sql.split()[0]."""
    r = run(client, sql)
    assert r.status_code in (400, 403), f"{sql!r} returned {r.status_code}: {r.text[:200]}"


def test_a_second_statement_cannot_ride_along(client):
    """`SELECT 1; DROP ...` passed the first-word check on the first statement."""
    r = run(client, "SELECT 1; DROP TABLE probe_business.dim_vessel")
    assert r.status_code == 400
    assert "one statement" in r.json()["detail"].lower()

    # and the table is still there
    assert run(client, "SELECT count(*) FROM probe_business.dim_vessel").status_code == 200


# --------------------------------------------------------------------------
# the row cap -- previously applied by editing the SQL string
# --------------------------------------------------------------------------

def test_a_trailing_semicolon_does_not_break_the_query(client):
    """Appending LIMIT produced `SELECT ...; LIMIT 1000` -- a syntax error."""
    r = run(client, "SELECT * FROM probe_business.dim_vessel;", limit=5)
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 5
    assert r.json()["truncated"] is True


def test_the_word_limit_in_a_string_does_not_defeat_the_cap(client):
    """`"LIMIT" not in sql.upper()` is a substring test over the whole query."""
    r = run(client, "SELECT 'LIMIT' AS note, vessel_key FROM probe_business.dim_vessel", limit=3)
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 3, "row cap was skipped because the SQL mentions LIMIT"
    assert r.json()["truncated"] is True


def test_a_column_named_limit_does_not_defeat_the_cap(client):
    r = run(client, 'SELECT vessel_key AS "limit" FROM probe_business.dim_vessel', limit=2)
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 2


def test_the_cap_is_bounded_by_max_rows(client):
    from datavloot_platform.crowsnest.routes.query import MAX_ROWS
    r = run(client, "SELECT * FROM range(100000)", limit=MAX_ROWS + 5_000)
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] <= MAX_ROWS


def test_truncated_is_false_when_everything_fits(client):
    r = run(client, "SELECT * FROM probe_business.dim_vessel", limit=500)
    assert r.json()["row_count"] == 50
    assert r.json()["truncated"] is False


# --------------------------------------------------------------------------
# injection on the endpoint the statement check never sees
# --------------------------------------------------------------------------

def test_list_columns_is_not_injectable(client):
    """table_name was spliced straight into the WHERE clause."""
    ok = client.get("/api/query/columns/probe_business.dim_vessel")
    assert ok.status_code == 200
    assert {c["name"] for c in ok.json()["columns"]} == {"vessel_key", "name"}

    r = client.get("/api/query/columns/x' OR '1'='1")
    assert r.status_code == 200, r.text
    assert r.json()["columns"] == [], "injected predicate matched rows"


def test_the_schema_lists_tables_and_columns_for_autocomplete(client):
    r = client.get("/api/query/schema")
    assert r.status_code == 200, r.text
    schemas = r.json()["schemas"]
    assert schemas["probe_business"]["dim_vessel"] == [
        {"name": "vessel_key", "type": "BIGINT"},
        {"name": "name", "type": "VARCHAR"},
    ]
    # A lake's own bookkeeping (ducklake_snapshot, ...) is not offered.
    assert not any(t.startswith("ducklake_") for tables in schemas.values() for t in tables)


def test_list_tables_still_works(client):
    r = client.get("/api/query/tables")
    assert r.status_code == 200
    assert any(t["name"] == "dim_vessel" for t in r.json()["tables"])


# --------------------------------------------------------------------------
# Host and Origin on loopback -- no sign-in there, so the browser is the risk
# --------------------------------------------------------------------------

LAPTOP = "http://127.0.0.1:8080"


@pytest.fixture
def make_laptop(client, monkeypatch):
    """The same warehouse, served as `datavloot start` does: on 127.0.0.1."""
    from datavloot_platform.crowsnest.server import create_app

    def make(dev_origin: str | None = None) -> TestClient:
        if dev_origin is None:
            monkeypatch.delenv("CROWSNEST_DEV_ORIGIN", raising=False)
        else:
            monkeypatch.setenv("CROWSNEST_DEV_ORIGIN", dev_origin)
        return TestClient(create_app(host="127.0.0.1"), base_url=LAPTOP)

    return make


@pytest.fixture
def laptop(make_laptop) -> TestClient:
    return make_laptop()


def test_a_foreign_host_is_misdirected(laptop):
    """A page whose own domain resolves to 127.0.0.1 sends its own name as Host."""
    r = laptop.post(
        "/api/query/execute",
        json={"sql": "SELECT 1"},
        headers={"Host": "evil.example:8080", "Origin": "http://evil.example:8080"},
    )
    assert r.status_code == 421, r.text


def test_a_misdirected_request_says_which_address_works(laptop):
    detail = laptop.get("/", headers={"Host": "0.0.0.0:8080"}).json()["detail"]
    assert "http://localhost:8080" in detail and "http://127.0.0.1:8080" in detail


@pytest.mark.parametrize("path", ["/", "/api/health", "/api/branding"])
def test_the_host_check_covers_every_route(laptop, path):
    assert laptop.get(path, headers={"Host": "evil.example:8080"}).status_code == 421


@pytest.mark.parametrize("host", [
    "localhost.:8080",
    "evil.example@localhost:8080",
    "localhost:8080@evil.example",
    "[::ffff:127.0.0.1]:8080",
    "[0:0:0:0:0:0:0:1]:8080",
    "127.1:8080",
    "2130706433:8080",
    "0x7f000001:8080",
    "localhost:notaport",
])
def test_other_spellings_of_loopback_are_misdirected(laptop, host):
    """Only the exact names pass: a resolver may read these as 127.0.0.1, a browser as a site."""
    assert laptop.get("/api/health", headers={"Host": host}).status_code == 421, host


@pytest.mark.parametrize("origin", [
    "http://evil.example",
    "http://evil.example:3001",
    "https://127.0.0.1:8080",
    "http://127.0.0.1:9999",
    "http://localhost:8080.evil.example",
    "http://evil.example@localhost:8080",
    "http://localhost.:8080",
    "null",
])
def test_a_cross_site_origin_is_refused(laptop, origin):
    r = laptop.post("/api/query/execute", json={"sql": "SELECT 1"}, headers={"Origin": origin})
    assert r.status_code == 403, f"{origin!r} returned {r.status_code}"


@pytest.mark.parametrize("host, origin", [
    ("127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("localhost:8080", "http://localhost:8080"),
    ("[::1]:8080", "http://[::1]:8080"),
    ("localhost:8080", None),
    ("localhost", None),
])
def test_the_dashboards_own_origin_and_no_origin_work(laptop, host, origin):
    headers = {"Host": host} | ({"Origin": origin} if origin else {})
    r = laptop.post("/api/query/execute", json={"sql": "SELECT 1"}, headers=headers)
    assert r.status_code == 200, r.text


def test_the_dev_server_origin_is_allowed_only_when_set(make_laptop):
    """`npm run dev`: next.config.js proxies /api with the Crows Nest's Host and its own Origin."""
    def post(client, origin):
        return client.post(
            "/api/query/execute",
            json={"sql": "SELECT 1"},
            headers={"Host": "localhost:8080", "Origin": origin},
        ).status_code

    assert post(make_laptop(), "http://localhost:3001") == 403

    dev = make_laptop("http://localhost:3001, http://127.0.0.1:3002")
    assert post(dev, "http://localhost:3001") == 200
    assert post(dev, "http://127.0.0.1:3002") == 200
    # Exact: another name or port on the same machine is not let in with it.
    assert post(dev, "http://127.0.0.1:3001") == 403
    assert post(dev, "http://localhost:3002") == 403


@pytest.mark.parametrize("value", [
    "http://evil.example:3001",
    "https://localhost:3001",
    "localhost:3001",
    "http://localhost:3001/app",
    "null",
])
def test_a_dev_origin_off_this_machine_is_an_error(monkeypatch, value):
    from datavloot_platform.crowsnest.loopback import dev_origins

    monkeypatch.setenv("CROWSNEST_DEV_ORIGIN", value)
    with pytest.raises(ValueError, match="CROWSNEST_DEV_ORIGIN"):
        dev_origins()


def test_the_cli_stops_on_a_bad_dev_origin(monkeypatch):
    import argparse

    from datavloot_platform import cli

    monkeypatch.setenv("CROWSNEST_DEV_ORIGIN", "http://evil.example:3001")
    with pytest.raises(SystemExit, match="^Error: CROWSNEST_DEV_ORIGIN"):
        cli.cmd_crowsnest(argparse.Namespace(host="127.0.0.1", port=8099, open=False))


# The ASGI scope directly, for what an HTTP client will not send.

def _guard():
    from datavloot_platform.crowsnest.loopback import LoopbackGuardMiddleware

    reached = []

    async def app(scope, receive, send):
        reached.append(scope["type"])
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    return LoopbackGuardMiddleware(app, bind_host="127.0.0.1"), reached


def _call(guard, scope_type, headers):
    import asyncio

    sent = []
    scope = {
        "type": scope_type,
        "path": "/",
        "headers": [(k.encode(), v.encode()) for k, v in headers],
        "server": ("127.0.0.1", 8080),
    }

    async def receive():
        return {"type": "websocket.connect"} if scope_type == "websocket" else {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(guard(scope, receive, send))
    return sent


@pytest.mark.parametrize("headers", [
    [],
    [("host", "evil.example"), ("host", "localhost:8080")],
    [("host", "localhost:8080"), ("host", "evil.example")],
], ids=["no Host", "foreign Host first", "foreign Host second"])
def test_a_missing_or_repeated_host_is_misdirected(headers, monkeypatch):
    monkeypatch.delenv("CROWSNEST_DEV_ORIGIN", raising=False)
    guard, reached = _guard()
    assert _call(guard, "http", headers)[0]["status"] == 421
    assert reached == []


def test_a_repeated_origin_is_refused(monkeypatch):
    monkeypatch.delenv("CROWSNEST_DEV_ORIGIN", raising=False)
    guard, reached = _guard()
    headers = [("host", "localhost:8080"), ("origin", "http://localhost:8080"), ("origin", "http://evil.example")]
    assert _call(guard, "http", headers)[0]["status"] == 403
    assert reached == []


@pytest.mark.parametrize("headers", [
    [("host", "evil.example:8080")],
    [("host", "localhost:8080"), ("origin", "http://evil.example")],
], ids=["bad Host", "bad Origin"])
def test_a_websocket_from_elsewhere_is_closed(headers, monkeypatch):
    monkeypatch.delenv("CROWSNEST_DEV_ORIGIN", raising=False)
    guard, reached = _guard()
    assert _call(guard, "websocket", headers) == [{"type": "websocket.close", "code": 1008}]
    assert reached == []


def test_a_websocket_from_the_dashboard_goes_through(monkeypatch):
    monkeypatch.delenv("CROWSNEST_DEV_ORIGIN", raising=False)
    guard, reached = _guard()
    _call(guard, "websocket", [("host", "localhost:8080"), ("origin", "http://localhost:8080")])
    assert reached == ["websocket"]


def test_a_non_loopback_bind_is_unaffected(client):
    """VM mode and the Falcon: public names, guarded by the token or the proxy."""
    from datavloot_platform.crowsnest.server import create_app
    remote = TestClient(create_app(host="0.0.0.0"))
    r = remote.get(
        "/api/query/tables",
        headers={"Host": "crowsnest.example.nl", "Origin": "https://crowsnest.example.nl"},
    )
    assert r.status_code == 200, r.text
