"""
Where a project's lake lives, and the attach every component uses.

The first block needs nothing installed. The second uses real DuckDB and checks
the behaviour storage.py's attach options exist for; each of those was found in
a prototype, not assumed. The dlt test is in the slow tier: it needs the full
optimist extra.
"""

import pathlib
import shutil

import pytest

from datavloot_platform import storage


@pytest.fixture
def project(tmp_path, monkeypatch) -> pathlib.Path:
    """A directory that looks like a project to storage.py: a dbt_project.yml with a name."""
    monkeypatch.delenv(storage.LAKE_DIR_ENV, raising=False)
    root = tmp_path / "sales"
    root.mkdir()
    (root / "dbt_project.yml").write_text("name: 'sales'\nversion: '1.0.0'\n", encoding="utf-8")
    return root


# --- paths --------------------------------------------------------------------

def test_the_project_is_found_from_a_subdirectory(project):
    (project / "notebooks").mkdir()
    assert storage.find_project_dir(project / "notebooks") == project.resolve()


def test_no_project_outside_one(tmp_path):
    assert storage.find_project_dir(tmp_path) is None


@pytest.mark.parametrize("line", ["name: 'sales'", 'name: "sales"', "name: sales"])
def test_the_catalog_is_named_after_the_dbt_project(project, line):
    (project / "dbt_project.yml").write_text(f"{line}\nversion: '1.0.0'\n", encoding="utf-8")
    assert storage.project_name(project) == "sales"


def test_the_lake_lives_in_the_project_by_default(project):
    assert storage.catalog_path(project) == (project / "lake" / "catalog.sqlite").resolve()
    assert storage.data_path(project) == (project / "lake" / "data").resolve()


def test_the_lake_directory_can_be_moved_by_environment(project, tmp_path, monkeypatch):
    monkeypatch.setenv(storage.LAKE_DIR_ENV, str(tmp_path / "volume"))
    assert storage.lake_dir(project) == (tmp_path / "volume").resolve()
    monkeypatch.setenv(storage.LAKE_DIR_ENV, "relative/lake")
    assert storage.lake_dir(project) == (project / "relative" / "lake").resolve(), (
        "a relative override is relative to the project, not to the current directory"
    )


def test_every_attach_carries_the_options_the_lake_needs(project):
    sql = storage.attach_statement(storage.catalog_path(project), storage.data_path(project), "sales")
    data = storage.data_path(project).as_posix()
    assert f"DATA_PATH '{data}/'" in sql, "the data path must be absolute"
    assert "OVERRIDE_DATA_PATH true" in sql
    assert "META_JOURNAL_MODE 'WAL'" in sql
    assert "READ_ONLY" not in sql
    assert "READ_ONLY" in storage.attach_statement(
        storage.catalog_path(project), storage.data_path(project), "sales", read_only=True
    )


# --- real DuckDB --------------------------------------------------------------

def _write(project, rows):
    con = storage.connect(project)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute("CREATE TABLE IF NOT EXISTS raw.t (i BIGINT)")
        con.execute(f"INSERT INTO raw.t SELECT range FROM range({rows})")
    finally:
        con.close()


def _count(project):
    con = storage.connect(project, read_only=True)
    try:
        return con.execute("SELECT count(*) FROM raw.t").fetchone()[0]
    finally:
        con.close()


def test_a_created_lake_is_in_wal_mode(project):
    """In SQLite's default mode a reader and a writer lock each other out."""
    pytest.importorskip("duckdb")
    import sqlite3

    storage.create(project)
    con = sqlite3.connect(storage.catalog_path(project))
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        con.close()


def test_the_current_directory_does_not_decide_where_data_goes(project, tmp_path, monkeypatch):
    """
    A relative data path follows the current directory, so a notebook and a
    pipeline started from different folders used to write to different places.
    """
    pytest.importorskip("duckdb")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    _write(project, 100)

    assert _count(project) == 100
    assert list(storage.data_path(project).rglob("*.parquet")), "no data file in the lake"
    assert not list(elsewhere.rglob("*.parquet")), "data was written next to the current directory"


def test_a_moved_project_keeps_its_data(project, tmp_path):
    """
    The catalog stores the data path it was created with; the override on every
    attach is what lets the same lake be read and written from a new location.
    """
    pytest.importorskip("duckdb")
    _write(project, 100)

    moved = tmp_path / "moved" / "sales"
    moved.parent.mkdir()
    shutil.move(str(project), str(moved))

    assert _count(moved) == 100
    _write(moved, 50)
    assert _count(moved) == 150


def test_a_reader_does_not_need_write_access_to_open_the_lake(project):
    """Notebooks and the Crows Nest attach read-only; WAL must not make that a write."""
    pytest.importorskip("duckdb")
    _write(project, 10)
    con = storage.connect(project, read_only=True)
    try:
        with pytest.raises(Exception):
            con.execute("INSERT INTO raw.t VALUES (1)")
    finally:
        con.close()


@pytest.mark.slow
def test_dlt_loads_into_the_lake_and_still_does_after_a_move(project, tmp_path):
    """
    dlt passes the data path but not the override, so without
    override_data_path a moved project failed with "DATA_PATH ... does not match".
    """
    dlt = pytest.importorskip("dlt")
    pytest.importorskip("pyarrow", reason="dlt's ducklake destination needs dlt[ducklake]")

    def load(root, n):
        pipeline = dlt.pipeline(
            pipeline_name=f"t{n}",
            destination=storage.dlt_destination(root),
            dataset_name="raw",
            pipelines_dir=str(tmp_path / "pipelines"),
        )
        pipeline.run([{"i": i} for i in range(n)], table_name="t")

    load(project, 100)
    assert _count(project) == 100

    moved = tmp_path / "moved" / "sales"
    moved.parent.mkdir()
    shutil.move(str(project), str(moved))
    load(moved, 50)
    assert _count(moved) == 150
