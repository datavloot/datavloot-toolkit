"""
The Crows Nest against a DuckLake catalog instead of a DuckDB file.

Fast tests cover the config discovery and the ATTACH statement. The one test
that opens a real (local) DuckLake needs the extension downloaded, so it is
marked slow like the other network-touching tests.
"""

import pathlib

import pytest

duckdb = pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest import db  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    for name in ("CROWSNEST_DUCKDB_PATH", "CROWSNEST_DUCKLAKE_CATALOG_PATH", "CROWSNEST_DUCKLAKE_ALIAS",
                 "CROWSNEST_DUCKLAKE_DATA_PATH", "CROWSNEST_DUCKLAKE_METADATA_SCHEMA", "DBT_TARGET",
                 "DATAVLOOT_VESSEL", "DUCKLAKE_PG_HOST", "DUCKLAKE_PG_PASSWORD", "DUCKLAKE_DATA_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    cn_config.reset_config()
    yield
    cn_config.reset_config()


# --------------------------------------------------------------------------
# ATTACH

def test_postgres_catalog_string_is_never_path_normalised():
    """
    The old code did `.replace("\\\\", "/")` on the catalog path. On a connection
    string that is harmless, but it also treated it as a file and added TYPE
    ducklake. A `ducklake:` string must pass through verbatim, spaces and all.
    """
    catalog = "ducklake:postgres:host=postgres port=5432 dbname=ducklake user=postgres password=p w"
    sql = db.attach_statement(catalog, "lake", read_only=True, data_path="/data/ducklake", metadata_schema="ducklake_x")
    assert sql.startswith(f"ATTACH IF NOT EXISTS '{catalog}' AS lake (")
    assert "TYPE ducklake" not in sql
    assert "READ_ONLY" in sql
    assert "DATA_PATH '/data/ducklake'" in sql and "OVERRIDE_DATA_PATH true" in sql
    assert "METADATA_SCHEMA 'ducklake_x'" in sql


def test_file_catalog_keeps_the_legacy_behaviour():
    sql = db.attach_statement("C:\\lake\\catalog.ducklake", "lakehouse", read_only=False)
    assert sql == "ATTACH IF NOT EXISTS 'C:/lake/catalog.ducklake' AS lakehouse (TYPE ducklake)"


def test_remote_hardening_keeps_the_network_and_closes_the_disk():
    assert "SET enable_external_access=false" in db._HARDENING
    assert "SET enable_external_access=false" not in db._HARDENING_REMOTE, "httpfs needs the network"
    assert "SET disabled_filesystems='LocalFileSystem'" in db._HARDENING_REMOTE
    assert db._HARDENING_REMOTE[-1] == "SET lock_configuration=true"


# --------------------------------------------------------------------------
# Discovery from profiles.yml

PROFILES = """
probe:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: probe.duckdb
      schema: probe
    valk:
      type: duckdb
      path: ":memory:"
      schema: probe
      attach:
        - path: "ducklake:postgres:host={{ env_var('DUCKLAKE_PG_HOST', 'localhost') }} dbname=ducklake password={{ env_var('DUCKLAKE_PG_PASSWORD') }}"
          alias: ducklake
          is_ducklake: true
          options:
            data_path: "{{ env_var('DUCKLAKE_DATA_PATH', '/data/ducklake') }}"
            metadata_schema: "{{ env_var('DUCKLAKE_METADATA_SCHEMA', 'ducklake_probe') }}"
"""


def test_render_env_var_jinja():
    import os
    os.environ.pop("PROBE_X", None)
    assert cn_config.render_env_var_jinja("a {{ env_var('PROBE_X', 'dflt') }} b") == "a dflt b"
    assert cn_config.render_env_var_jinja("{{env_var(\"PROBE_X\")}}") == ""
    os.environ["PROBE_X"] = "v"
    try:
        assert cn_config.render_env_var_jinja("{{ env_var('PROBE_X', 'dflt') }}") == "v"
    finally:
        del os.environ["PROBE_X"]


def test_default_target_is_the_duckdb_file(tmp_path):
    (tmp_path / "profiles.yml").write_text(PROFILES, encoding="utf-8")
    config = cn_config.get_config()
    assert not config.uses_ducklake
    assert config.duckdb_path.endswith("probe.duckdb")
    assert config.elementary_schema == "probe_elementary"


def test_dbt_target_valk_switches_to_the_attached_catalog(tmp_path, monkeypatch):
    """With DBT_TARGET=valk the Crows Nest reads the catalog dbt writes, no CROWSNEST_* needed."""
    (tmp_path / "profiles.yml").write_text(PROFILES, encoding="utf-8")
    monkeypatch.setenv("DBT_TARGET", "valk")
    monkeypatch.setenv("DUCKLAKE_PG_HOST", "postgres")
    monkeypatch.setenv("DUCKLAKE_PG_PASSWORD", "pw")
    config = cn_config.get_config()

    assert config.uses_ducklake
    assert config.ducklake_catalog_path == "ducklake:postgres:host=postgres dbname=ducklake password=pw"
    assert config.ducklake_alias == "ducklake"
    assert config.ducklake_data_path == "/data/ducklake"
    assert config.ducklake_metadata_schema == "ducklake_probe"
    assert "password" not in config.warehouse_label or "***" in config.warehouse_label


def test_valk_vessel_takes_over(tmp_path, monkeypatch):
    (tmp_path / "datavloot.yml").write_text("vessel: valk\nvalk:\n  domain: probe.valk.test\n", encoding="utf-8")
    (tmp_path / "dbt_project.yml").write_text("name: probe\n", encoding="utf-8")
    config = cn_config.get_config()
    assert config.is_valk and config.uses_ducklake
    assert config.ducklake_alias == "ducklake"
    assert "Valk" in config.warehouse_label


# --------------------------------------------------------------------------
# A real local DuckLake through the whole stack

@pytest.mark.slow
def test_query_route_reads_a_local_ducklake(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    catalog = tmp_path / "catalog.ducklake"
    data = tmp_path / "data"
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake")
    con.execute(f"ATTACH 'ducklake:{catalog.as_posix()}' AS lake (DATA_PATH '{data.as_posix()}')")
    con.execute("CREATE SCHEMA lake.probe_business")
    con.execute("CREATE TABLE lake.probe_business.dim_vessel AS SELECT 1 AS vessel_key, 'v1' AS name")
    con.close()

    monkeypatch.setenv("CROWSNEST_DUCKLAKE_CATALOG_PATH", f"ducklake:{catalog.as_posix()}")
    monkeypatch.setenv("CROWSNEST_DUCKLAKE_DATA_PATH", data.as_posix())
    monkeypatch.setenv("CROWSNEST_DUCKLAKE_ALIAS", "lake")
    monkeypatch.delenv("CROWSNEST_AUTH_TOKEN", raising=False)
    cn_config.reset_config()
    from datavloot_platform.crowsnest.server import create_app
    client = TestClient(create_app())

    ok = client.post("/api/query/execute", json={"sql": "SELECT name FROM probe_business.dim_vessel"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["rows"] == [["v1"]]

    leak = client.post("/api/query/execute", json={"sql": f"COPY (SELECT 1) TO '{(tmp_path / 'x.csv').as_posix()}'"})
    assert leak.status_code in (400, 403), "the filesystem must stay closed on a DuckLake connection"
    assert not (tmp_path / "x.csv").exists()

    assert client.get("/api/health").json()["services"]["duckdb"] == "ok"
