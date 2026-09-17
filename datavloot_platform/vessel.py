"""
datavloot.yml: the one config surface that says which vessel a project sails on.

    vessel: optimist   -> everything local, one DuckDB file, no auth (unchanged)
    vessel: valk       -> the same project on an SRDP Compose stack: DuckLake on
                          Postgres, Parquet on a volume or S3 bucket, Zitadel SSO

The README promise is that a project moves between vessels with a config change,
not a rewrite. Everything in this module exists to make that literally true:
dbt, dlt, plain Dagster assets and the Crows Nest all ask this module where the
warehouse is instead of hardcoding a `.duckdb` path.

Runtime settings that are *secrets* or *deployment-specific* never live in
datavloot.yml. They arrive as environment variables, and the names are SRDP's own
(`DUCKLAKE_PG_HOST`, `DUCKLAKE_DATA_PATH`, ...) so a datavloot project drops into
an SRDP container unchanged:

    DATAVLOOT_VESSEL           overrides the `vessel:` key (the Compose overlay sets it)
    DUCKLAKE_PG_HOST / _PORT / _DB / _USER / _PASSWORD
                               the Postgres that holds the DuckLake catalog
    DUCKLAKE_DATA_PATH         where the Parquet files go (a path or an s3:// URL)
    DUCKLAKE_METADATA_SCHEMA   metadata schema inside the catalog database
    DATAVLOOT_S3_KEY_ID / DATAVLOOT_S3_SECRET
                               object-storage credentials, when storage.kind is s3
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any

import yaml

CONFIG_FILENAME = "datavloot.yml"
VESSELS = ("optimist", "valk")

# The SRDP commit the Valk overlay is rendered against. The overlay shadows service
# names, network names and Traefik label keys from SRDP's deploy/docker compose
# file, so bumping this is a deliberate act: re-read their compose, re-run the
# render tests, then move the pin.
SRDP_REPO = "https://github.com/srdp-hub/srdp.git"
SRDP_REF = "896ceea82b73fdb5b53502bdd9cc5882d90efae8"  # main, 2026-09-04

DEFAULT_CATALOG_DB = "ducklake"
DEFAULT_CATALOG_ALIAS = "ducklake"


class VesselConfigError(ValueError):
    """datavloot.yml is missing something, or says something impossible."""


@dataclasses.dataclass(frozen=True)
class StorageConfig:
    kind: str = "local"                 # local | s3
    data_path: str = "/data/ducklake"   # local: path inside the containers
    bucket: str | None = None
    prefix: str | None = None
    endpoint: str | None = None         # s3.nl-ams.scw.cloud, fsn1.your-objectstorage.com, ...
    region: str | None = None
    url_style: str = "path"

    @property
    def url(self) -> str:
        """The DuckLake DATA_PATH this storage resolves to."""
        if self.kind == "s3":
            prefix = (self.prefix or "").strip("/")
            return f"s3://{self.bucket}/{prefix}/" if prefix else f"s3://{self.bucket}/"
        return self.data_path


@dataclasses.dataclass(frozen=True)
class ValkConfig:
    domain: str
    acme_email: str | None
    metadata_schema: str
    storage: StorageConfig
    default_role: str          # reader | none
    srdp_repo: str
    srdp_ref: str
    catalog_alias: str = DEFAULT_CATALOG_ALIAS

    def host(self, service: str) -> str:
        return f"{service}.{self.domain}"

    @property
    def issuer(self) -> str:
        return f"https://{self.host('auth')}"


@dataclasses.dataclass(frozen=True)
class VesselConfig:
    vessel: str
    project_dir: pathlib.Path
    name: str
    valk: ValkConfig | None = None

    @property
    def is_valk(self) -> bool:
        return self.vessel == "valk"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def find_config(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """Walk up from `start` (default: cwd) to the first datavloot.yml."""
    here = pathlib.Path(start or pathlib.Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        path = candidate / CONFIG_FILENAME
        if path.is_file():
            return path
    return None


def _project_name(project_dir: pathlib.Path, raw: dict) -> str:
    """The dbt project name is the catalog and profile name; fall back to the dir."""
    explicit = raw.get("name")
    if explicit:
        return str(explicit)
    dbt_project = project_dir / "dbt_project.yml"
    if dbt_project.is_file():
        try:
            doc = yaml.safe_load(dbt_project.read_text(encoding="utf-8")) or {}
            if doc.get("name"):
                return str(doc["name"])
        except yaml.YAMLError:
            pass
    return project_dir.name.replace("-", "_").replace(" ", "_").lower()


def _storage(raw: dict, name: str) -> StorageConfig:
    kind = str(raw.get("kind", "local")).lower()
    if kind not in ("local", "s3"):
        raise VesselConfigError(f"valk.storage.kind must be 'local' or 's3', got {kind!r}")
    if kind == "s3":
        missing = [k for k in ("bucket", "endpoint") if not raw.get(k)]
        if missing:
            raise VesselConfigError(
                "valk.storage.kind is s3, so these keys are required: " + ", ".join(missing)
            )
    return StorageConfig(
        kind=kind,
        data_path=str(raw.get("data_path", "/data/ducklake")),
        bucket=raw.get("bucket"),
        prefix=raw.get("prefix", name if kind == "s3" else None),
        endpoint=raw.get("endpoint"),
        region=raw.get("region"),
        url_style=str(raw.get("url_style", "path")),
    )


def _valk(raw: Any, name: str) -> ValkConfig:
    if not isinstance(raw, dict):
        raise VesselConfigError("vessel is valk but there is no `valk:` block in datavloot.yml")
    domain = str(raw.get("domain") or "").strip()
    if not domain or "/" in domain or domain.startswith("http"):
        raise VesselConfigError(
            "valk.domain must be a bare host name such as 'valk.example.nl' "
            "(services are published as crowsnest.<domain>, dagster.<domain>, auth.<domain>)"
        )
    access = raw.get("access") or {}
    default_role = str(access.get("default_role", "reader")).lower()
    if default_role not in ("reader", "none"):
        raise VesselConfigError("valk.access.default_role must be 'reader' or 'none'")
    catalog = raw.get("catalog") or {}
    srdp = raw.get("srdp") or {}
    return ValkConfig(
        domain=domain,
        acme_email=(raw.get("acme_email") or None),
        metadata_schema=str(catalog.get("metadata_schema") or f"ducklake_{name}"),
        storage=_storage(raw.get("storage") or {}, name),
        default_role=default_role,
        srdp_repo=str(srdp.get("repo") or SRDP_REPO),
        srdp_ref=str(srdp.get("ref") or SRDP_REF),
        catalog_alias=str(catalog.get("alias") or DEFAULT_CATALOG_ALIAS),
    )


def load_vessel(project_dir: pathlib.Path | str | None = None) -> VesselConfig:
    """
    Read datavloot.yml for the project at `project_dir` (default: search upward from cwd).

    A missing file means Optimist: every project that predates this file keeps
    working exactly as before. `DATAVLOOT_VESSEL` in the environment wins over the
    file, which is how the Compose overlay flips a checked-out project to valk
    without editing it.
    """
    if project_dir is not None:
        project_dir = pathlib.Path(project_dir).resolve()
        path = project_dir / CONFIG_FILENAME
        path = path if path.is_file() else None
    else:
        path = find_config()
        project_dir = path.parent if path else pathlib.Path.cwd().resolve()

    raw: dict = {}
    if path is not None:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise VesselConfigError(f"{path} is not valid YAML: {exc}") from exc
        if loaded is not None and not isinstance(loaded, dict):
            raise VesselConfigError(f"{path} must be a mapping at the top level")
        raw = loaded or {}

    vessel = str(os.environ.get("DATAVLOOT_VESSEL") or raw.get("vessel") or "optimist").lower()
    if vessel not in VESSELS:
        raise VesselConfigError(f"unknown vessel {vessel!r}; choose one of {', '.join(VESSELS)}")

    name = _project_name(project_dir, raw)
    valk = _valk(raw.get("valk"), name) if vessel == "valk" else None
    return VesselConfig(vessel=vessel, project_dir=project_dir, name=name, valk=valk)


# ---------------------------------------------------------------------------
# Runtime: where is the warehouse?
# ---------------------------------------------------------------------------

def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name) or default
    if required and not value:
        raise VesselConfigError(
            f"{name} is not set. On the Valk this comes from deploy/valk/.env via the Compose overlay."
        )
    return value


def catalog_attach_string() -> str:
    """
    The DuckLake catalog as DuckDB's ATTACH wants it, built from the DUCKLAKE_PG_*
    environment. Contains the password: never log it, never write it to a file.
    """
    host = _env("DUCKLAKE_PG_HOST", "localhost")
    port = _env("DUCKLAKE_PG_PORT", "5432")
    db = _env("DUCKLAKE_PG_DB", DEFAULT_CATALOG_DB)
    user = _env("DUCKLAKE_PG_USER", "postgres")
    password = _env("DUCKLAKE_PG_PASSWORD", required=True)
    return f"ducklake:postgres:host={host} port={port} dbname={db} user={user} password={password}"


def catalog_dsn() -> str:
    """The same catalog as a libpq/SQLAlchemy URL, for dlt and psycopg2."""
    host = _env("DUCKLAKE_PG_HOST", "localhost")
    port = _env("DUCKLAKE_PG_PORT", "5432")
    db = _env("DUCKLAKE_PG_DB", DEFAULT_CATALOG_DB)
    user = _env("DUCKLAKE_PG_USER", "postgres")
    password = _env("DUCKLAKE_PG_PASSWORD", required=True)
    return f"postgres://{user}:{password}@{host}:{port}/{db}"


def data_path() -> str:
    return _env("DUCKLAKE_DATA_PATH", "/data/ducklake") or "/data/ducklake"


def metadata_schema(config: VesselConfig | None = None) -> str:
    explicit = os.environ.get("DUCKLAKE_METADATA_SCHEMA")
    if explicit:
        return explicit
    if config is not None and config.valk is not None:
        return config.valk.metadata_schema
    return "ducklake_" + (config.name if config else "main")


def is_remote(path: str) -> bool:
    return "://" in path and not path.startswith("file://")


def s3_secret_sql(config: VesselConfig | None) -> str | None:
    """
    A `CREATE SECRET` for DuckDB's httpfs, when the data path is an S3 bucket.

    Endpoint, region and URL style are deployment facts from datavloot.yml; the key
    pair is a secret from the environment. Returns None when storage is local.
    """
    path = data_path()
    if not is_remote(path):
        return None
    key_id = _env("DATAVLOOT_S3_KEY_ID", required=True)
    secret = _env("DATAVLOOT_S3_SECRET", required=True)
    storage = config.valk.storage if (config and config.valk) else StorageConfig(kind="s3")
    parts = [
        "TYPE s3",
        f"KEY_ID '{key_id}'",
        f"SECRET '{secret}'",
        f"URL_STYLE '{storage.url_style}'",
        "USE_SSL true",
    ]
    endpoint = _env("DATAVLOOT_S3_ENDPOINT", storage.endpoint)
    region = _env("DATAVLOOT_S3_REGION", storage.region)
    if endpoint:
        parts.append(f"ENDPOINT '{endpoint}'")
    if region:
        parts.append(f"REGION '{region}'")
    return "CREATE OR REPLACE SECRET datavloot_valk (" + ", ".join(parts) + ")"


def attach_ducklake(conn, config: VesselConfig | None = None, *, read_only: bool = False, alias: str | None = None):
    """
    Attach the shared DuckLake catalog to an open DuckDB connection and `USE` it.

    Loads the extensions, creates the S3 secret when storage is remote, and passes
    DATA_PATH plus METADATA_SCHEMA so dbt, dlt, plain assets and the Crows Nest all
    land in the same catalog. Returns the connection.
    """
    alias = alias or (config.valk.catalog_alias if config and config.valk else DEFAULT_CATALOG_ALIAS)
    path = data_path()
    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")
    if is_remote(path):
        conn.execute("INSTALL httpfs")
        conn.execute("LOAD httpfs")
        secret = s3_secret_sql(config)
        if secret:
            conn.execute(secret)
    options = [
        f"DATA_PATH '{path}'",
        "OVERRIDE_DATA_PATH true",
        f"METADATA_SCHEMA '{metadata_schema(config)}'",
    ]
    if read_only:
        options.append("READ_ONLY")
    conn.execute(f"ATTACH IF NOT EXISTS '{catalog_attach_string()}' AS {alias} ({', '.join(options)})")
    conn.execute(f"USE {alias}")
    return conn


def connect(project_dir: pathlib.Path | str | None, duckdb_path: pathlib.Path | str, *, read_only: bool = False):
    """
    Open the project's warehouse, wherever this vessel keeps it.

        con = connect(PROJECT_DIR, DB_PATH)
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")   # same code on both vessels

    Optimist: the `.duckdb` file. Valk: an in-memory DuckDB with the DuckLake
    catalog attached and selected, so unqualified `schema.table` names resolve
    inside the shared catalog.
    """
    import duckdb

    config = load_vessel(project_dir)
    if not config.is_valk:
        return duckdb.connect(str(duckdb_path), read_only=read_only)
    return attach_ducklake(duckdb.connect(), config, read_only=read_only)


def dlt_destination(project_dir: pathlib.Path | str | None, duckdb_path: pathlib.Path | str):
    """
    The dlt destination for this vessel.

        dlt.pipeline(..., destination=dlt_destination(PROJECT_DIR, DB_PATH))

    Optimist: dlt's duckdb destination on the project file. Valk: dlt's ducklake
    destination on the same Postgres catalog and data path everything else uses,
    with the metadata schema pinned so dbt sees what dlt loaded.
    """
    config = load_vessel(project_dir)
    if not config.is_valk:
        from dlt.destinations import duckdb as duckdb_destination
        return duckdb_destination(credentials=str(duckdb_path))

    from dlt.destinations import ducklake
    from dlt.destinations.impl.ducklake.configuration import DuckLakeCredentials

    storage: Any = data_path()
    if is_remote(storage):
        from dlt.common.configuration.specs import AwsCredentials
        from dlt.common.storages.configuration import FilesystemConfiguration

        s3 = config.valk.storage
        creds = AwsCredentials(
            aws_access_key_id=_env("DATAVLOOT_S3_KEY_ID", required=True),
            aws_secret_access_key=_env("DATAVLOOT_S3_SECRET", required=True),
            endpoint_url=(lambda e: f"https://{e}" if e and "://" not in e else e)(
                _env("DATAVLOOT_S3_ENDPOINT", s3.endpoint)
            ),
            region_name=_env("DATAVLOOT_S3_REGION", s3.region),
        )
        storage = FilesystemConfiguration(bucket_url=storage, credentials=creds)
    else:
        storage = pathlib.Path(storage).as_uri() if not storage.startswith("file://") else storage

    credentials = DuckLakeCredentials(
        ducklake_name=config.valk.catalog_alias,
        metadata_schema=metadata_schema(config),
        catalog=catalog_dsn(),
        storage=storage,
    )
    return ducklake(credentials=credentials)


def ensure_catalog_database() -> None:
    """
    Create the DuckLake catalog database in Postgres if it is missing.

    SRDP's compose creates the `zitadel` and `dagster` databases at first boot and
    leaves `ducklake` to whoever attaches first (their IO manager does this too).
    The Valk entrypoint calls this before dbt so the first `ATTACH` succeeds.
    """
    import psycopg2
    from psycopg2 import sql

    db = _env("DUCKLAKE_PG_DB", DEFAULT_CATALOG_DB)
    conn = psycopg2.connect(
        host=_env("DUCKLAKE_PG_HOST", "localhost"),
        port=_env("DUCKLAKE_PG_PORT", "5432"),
        user=_env("DUCKLAKE_PG_USER", "postgres"),
        password=_env("DUCKLAKE_PG_PASSWORD", required=True),
        dbname="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    finally:
        conn.close()
