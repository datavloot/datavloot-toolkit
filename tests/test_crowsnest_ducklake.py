"""
The Crows Nest against a DuckLake catalog instead of a DuckDB file.

Fast tests cover the config discovery and the connection hardening. Querying a
real project lake is covered by test_crowsnest_security.py.
"""

import pytest

duckdb = pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest import db  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    for name in ("CROWSNEST_DUCKDB_PATH", "CROWSNEST_DUCKLAKE_CATALOG_PATH", "CROWSNEST_DUCKLAKE_ALIAS",
                 "CROWSNEST_DUCKLAKE_DATA_PATH", "DBT_TARGET", "DATAVLOOT_LAKE_DIR",
                 "DATAVLOOT_VESSEL", "DUCKLAKE_PG_HOST", "DUCKLAKE_PG_PASSWORD", "DUCKLAKE_DATA_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    cn_config.reset_config()
    yield
    cn_config.reset_config()


# --------------------------------------------------------------------------
# Hardening

def test_remote_hardening_keeps_the_network_and_closes_the_disk():
    assert "SET enable_external_access=false" in db._HARDENING
    assert "SET enable_external_access=false" not in db._HARDENING_REMOTE, "httpfs needs the network"
    assert "SET disabled_filesystems='LocalFileSystem'" in db._HARDENING_REMOTE
    assert db._HARDENING_REMOTE[-1] == "SET lock_configuration=true"


# --------------------------------------------------------------------------
# Discovery

def test_without_a_lake_or_a_vessel_the_duckdb_file_is_used(tmp_path):
    (tmp_path / "profiles.yml").write_text(
        "probe:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n"
        "      path: probe.duckdb\n      schema: probe\n",
        encoding="utf-8",
    )
    config = cn_config.get_config()
    assert not config.uses_ducklake
    assert config.duckdb_path.endswith("probe.duckdb")
    assert config.elementary_schema == "probe_elementary"


def test_valk_vessel_takes_over(tmp_path, monkeypatch):
    (tmp_path / "datavloot.yml").write_text("vessel: valk\nvalk:\n  domain: probe.valk.test\n", encoding="utf-8")
    (tmp_path / "dbt_project.yml").write_text("name: probe\n", encoding="utf-8")
    config = cn_config.get_config()
    assert config.is_valk and config.uses_ducklake
    assert config.ducklake_alias == "ducklake"
    assert config.ducklake_catalog_path is None, "the Valk attaches through vessel.py, not a lake/ folder"
    assert "Valk" in config.warehouse_label
