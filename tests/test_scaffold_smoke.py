"""
End-to-end: does a fresh project actually build a warehouse?

This is the test that would have caught the pair of bugs the scaffold shipped
with. They were fixed one at a time, and fixing the first without the second
turned a loud failure (a parse error) into a silent one (a run that reports
tables built and writes nothing to disk).

Marked `slow`: it runs dbt deps/parse/run and takes a few minutes.
"""

import pathlib
import re
import shutil

import pytest

from .conftest import _scaffold, run_dbt, use_local_optimist

# Imported here rather than at the top so the fast suite can be collected and run
# without the optimist extras installed -- the lint job installs only pytest and
# pyyaml, and a module-level `import duckdb` would fail collection for everyone.
duckdb = pytest.importorskip("duckdb", reason="duckdb is not installed")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("dbt") is None, reason="dbt is not installed"),
]

# Expected for a project with no sources yet: the source layer config matches no
# resources because the user has not added a model. Anything else is a template bug.
EXPECTED_WARNINGS = [
    re.compile(r"unused configuration paths?", re.I),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> pathlib.Path:
    """A scaffolded project taken all the way through `dbt run`."""
    project = _scaffold(tmp_path_factory.mktemp("smoke") / "probe", "probe")
    use_local_optimist(project)

    deps = run_dbt("deps", cwd=project)
    assert deps.returncode == 0, f"dbt deps failed:\n{deps.stdout[-3000:]}"

    run = run_dbt("run", cwd=project)
    assert run.returncode == 0, f"dbt run failed:\n{run.stdout[-3000:]}"

    return project


def test_the_warehouse_file_exists(built: pathlib.Path):
    """
    The whole point. `dbt run` must leave a database on disk.

    With `path: ":memory:"` this ran to "Completed successfully", reported two
    tables built, and left nothing behind -- after which the Crows Nest showed an
    empty catalog with no error explaining why.
    """
    db = built / "probe.duckdb"
    assert db.is_file(), (
        f"no probe.duckdb in {built}; the project persisted nothing. "
        f"Files present: {sorted(p.name for p in built.iterdir())}"
    )
    assert db.stat().st_size > 0


def test_the_builtin_dimensions_have_rows(built: pathlib.Path):
    """dim_date and dim_time are built by macros; confirm they materialised."""
    con = duckdb.connect(str(built / "probe.duckdb"), read_only=True)
    try:
        found = {
            name: schema
            for schema, name in con.execute(
                "SELECT table_schema, table_name FROM information_schema.tables"
            ).fetchall()
        }
        for model in ("dim_date", "dim_time"):
            assert model in found, f"{model} was not built; tables: {sorted(found)}"
            rows = con.execute(f'SELECT count(*) FROM "{found[model]}"."{model}"').fetchone()[0]
            assert rows > 0, f"{model} is empty"
    finally:
        con.close()


def test_no_layer_landed_in_the_bare_catalog_schema(built: pathlib.Path):
    """
    A schema named after the database must never be created.

    DuckDB refuses two-part names when a catalog and a schema share a name:
    `Ambiguous reference to catalog or schema "probe"`. dbt itself is fine, since
    it emits three-part names -- this breaks the query editor and notebooks.
    """
    con = duckdb.connect(str(built / "probe.duckdb"), read_only=True)
    try:
        schemas = {
            r[0] for r in con.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE catalog_name = 'probe'"
            ).fetchall()
        }
    finally:
        con.close()

    assert "probe" not in schemas, (
        "a schema named 'probe' exists inside the catalog 'probe', so two-part "
        f"names are ambiguous. Schemas: {sorted(schemas)}"
    )


def test_parse_emits_no_unexpected_warnings(built: pathlib.Path):
    """
    A fresh project's first output should be clean.

    The source template declared a literal stg_<source_name>__<table_name> with
    tests attached, so dbt registered two tests against a model that does not
    exist and parse emitted three warnings before the user had written anything.
    """
    parse = run_dbt("parse", cwd=built)
    assert parse.returncode == 0, f"dbt parse failed:\n{parse.stdout[-3000:]}"

    warnings = [
        line.strip() for line in parse.stdout.splitlines()
        if "[WARNING]" in line or "Did not find matching node" in line
    ]
    unexpected = [
        w for w in warnings if not any(p.search(w) for p in EXPECTED_WARNINGS)
    ]

    assert unexpected == [], (
        "unexpected warnings from a fresh scaffold:\n  " + "\n  ".join(unexpected)
    )
