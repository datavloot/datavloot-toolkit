"""
Where a project's data lives, and how every component attaches to it.

The lake is DuckLake: a SQLite catalog and Parquet files, both in
<project>/lake/ (or DATAVLOOT_LAKE_DIR). dbt attaches it from profiles.yml;
everything else -- dlt, notebooks, the Crows Nest -- goes through this module,
so the attach options below are written down once.

What the attach relies on, each verified against DuckDB 1.5 with the ducklake
and sqlite extensions:

  - WAL journal mode on the catalog. In SQLite's default mode a reader and a
    writer lock each other out: a notebook stalls for seconds per query during a
    Dagster run. The mode is stored in the catalog file at creation; passing it
    on every attach also repairs a catalog that was created without it.
  - An absolute DATA_PATH with OVERRIDE_DATA_PATH on every attach. A relative
    data path resolves against the current directory, so a notebook and a
    pipeline started from different folders would write to different places.
    The override applies to the session only, and the file paths inside the
    catalog are relative to the data path, so a moved project keeps working.
  - One commit at a time. A second process committing at the same moment fails
    with "database is locked" instead of waiting; neither DuckLake's retries nor
    a SQLite busy timeout change that. Writers have to take turns.

duckdb and dlt are imported lazily, so the CLI and the fast test tier work
without the optimist extra.
"""

import os
import pathlib
import re

from datavloot_platform import extensions

LAKE_DIR_ENV = "DATAVLOOT_LAKE_DIR"


def find_project_dir(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """The nearest directory at or above `start` (default: cwd) with a dbt_project.yml."""
    here = pathlib.Path(start or pathlib.Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "dbt_project.yml").is_file():
            return candidate
    return None


def project_name(project_dir: pathlib.Path) -> str:
    """The dbt project name, which is also the catalog name the lake is attached as."""
    text = (pathlib.Path(project_dir) / "dbt_project.yml").read_text(encoding="utf-8")
    match = re.search(r"^name:\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", text, re.M)
    if not match:
        raise ValueError(f"no project name in {project_dir / 'dbt_project.yml'}")
    return match.group(1)


def lake_dir(project_dir: pathlib.Path) -> pathlib.Path:
    """<project>/lake, or DATAVLOOT_LAKE_DIR (relative to the project) when set."""
    override = os.environ.get(LAKE_DIR_ENV)
    path = pathlib.Path(override) if override else pathlib.Path("lake")
    if not path.is_absolute():
        path = pathlib.Path(project_dir) / path
    return path.resolve()


def catalog_path(project_dir: pathlib.Path) -> pathlib.Path:
    return lake_dir(project_dir) / "catalog.sqlite"


def data_path(project_dir: pathlib.Path) -> pathlib.Path:
    return lake_dir(project_dir) / "data"


def attach_statement(
    catalog: pathlib.Path, data: pathlib.Path, alias: str, *, read_only: bool = False
) -> str:
    """The ATTACH for a lake, with the options every attach needs (see the module docstring)."""
    options = [
        f"DATA_PATH '{pathlib.Path(data).as_posix()}/'",
        "OVERRIDE_DATA_PATH true",
        "META_JOURNAL_MODE 'WAL'",
    ]
    if read_only:
        options.append("READ_ONLY")
    return (
        f"ATTACH 'ducklake:sqlite:{pathlib.Path(catalog).as_posix()}' AS {alias} "
        f"({', '.join(options)})"
    )


def connect(project_dir: pathlib.Path | None = None, *, read_only: bool = False):
    """
    A DuckDB connection with the project's lake attached and selected.

    Queries can then name tables as `schema.table`, as they did against the
    project's .duckdb file.
    """
    import duckdb

    project_dir = _resolve(project_dir)
    alias = project_name(project_dir)
    conn = duckdb.connect()
    for name in extensions.REQUIRED:
        extensions.ensure_loaded(conn, name)
    if not read_only:
        lake_dir(project_dir).mkdir(parents=True, exist_ok=True)
    conn.execute(
        attach_statement(catalog_path(project_dir), data_path(project_dir), alias, read_only=read_only)
    )
    conn.execute(f"USE {alias}")
    return conn


def create(project_dir: pathlib.Path) -> None:
    """Create the project's lake if it does not exist yet, so readers find one before the first run."""
    connect(project_dir).close()


def dlt_destination(project_dir: pathlib.Path | None = None):
    """A dlt destination that loads into the project's lake."""
    from dlt.destinations import ducklake
    from dlt.destinations.impl.ducklake.configuration import DuckLakeCredentials

    project_dir = _resolve(project_dir)
    data = data_path(project_dir)
    data.mkdir(parents=True, exist_ok=True)
    return ducklake(
        credentials=DuckLakeCredentials(
            ducklake_name=project_name(project_dir),
            catalog=f"sqlite:///{catalog_path(project_dir).as_posix()}",
            storage=data.as_posix(),
        ),
        # dlt passes the data path but not the override; without it a moved
        # project fails with "DATA_PATH ... does not match".
        override_data_path=True,
    )


def _resolve(project_dir: pathlib.Path | None) -> pathlib.Path:
    if project_dir is not None:
        return pathlib.Path(project_dir).resolve()
    found = find_project_dir()
    if found is None:
        raise FileNotFoundError(
            "No dbt_project.yml in this directory or above it; pass the project directory."
        )
    return found
