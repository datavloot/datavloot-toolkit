"""
Auto-discovers configuration from the project directory where `datavloot launch`
is invoked, with environment variable overrides.

Discovery order:
  1. datavloot.yml      → on the Valk, the shared DuckLake catalog described by the
                          DUCKLAKE_* environment (see vessel.py); this wins
  2. The project's lake → <project>/lake/catalog.sqlite (see storage.py), when it exists
  3. profiles.yml       → DuckDB file path (outputs.dev.path) and target schema, for
                          projects still on a single .duckdb file
  4. Defaults           → Dagster on localhost:3000, Marimo on localhost:2718
  5. Env vars           → CROWSNEST_* overrides

Elementary schema:
  dbt's default generate_schema_name produces <target_schema>_<custom_schema>, so a
  project with schema: noaa and `models: elementary: +schema: elementary` writes
  Elementary tables to noaa_elementary.  We infer this automatically from profiles.yml
  so no manual configuration is needed.  Override with CROWSNEST_ELEMENTARY_SCHEMA.

Authentication (see auth.py):
  CROWSNEST_AUTH_TOKEN         one shared token; the Optimist-on-a-VM mode
  CROWSNEST_OIDC_ISSUER        validate Zitadel tokens instead; the Valk mode
  CROWSNEST_OIDC_AUDIENCE      optional expected `aud`
  CROWSNEST_OIDC_DEFAULT_ROLE  role for a user without one: reader (default) or none
  CROWSNEST_OIDC_INSECURE_TLS  "true" to accept mkcert certificates on the issuer
"""

import os
import pathlib
from typing import Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


_config: Optional["CrowsnestConfig"] = None



class CrowsnestConfig:
    def __init__(
        self,
        duckdb_path: str,
        dagster_graphql_url: str,
        elementary_schema: str,
        marimo_url: str,
        ducklake_catalog_path: Optional[str],
        ducklake_alias: str,
        ducklake_data_path: Optional[str] = None,
        dagster_public_url: str = "http://localhost:3000",
        vessel=None,
    ):
        self.duckdb_path = duckdb_path
        self.dagster_graphql_url = dagster_graphql_url
        self.elementary_schema = elementary_schema
        self.marimo_url = marimo_url
        self.ducklake_catalog_path = ducklake_catalog_path
        self.ducklake_alias = ducklake_alias
        self.ducklake_data_path = ducklake_data_path
        self.dagster_public_url = dagster_public_url
        self.vessel = vessel

    @property
    def is_valk(self) -> bool:
        return bool(self.vessel is not None and self.vessel.is_valk)

    @property
    def uses_ducklake(self) -> bool:
        """True when queries go to a DuckLake catalog rather than a DuckDB file."""
        return self.is_valk or bool(self.ducklake_catalog_path)

    @property
    def warehouse_label(self) -> str:
        """Human-readable description of the warehouse, safe to print (no secrets)."""
        if self.is_valk:
            host = os.environ.get("DUCKLAKE_PG_HOST", "localhost")
            db = os.environ.get("DUCKLAKE_PG_DB", "ducklake")
            return f"DuckLake catalog on Postgres {host}/{db} (Valk)"
        if self.ducklake_catalog_path:
            return f"Lake {self.ducklake_catalog_path} (as {self.ducklake_alias})"
        return f"DuckDB file {self.duckdb_path}"

    @classmethod
    def discover(cls) -> "CrowsnestConfig":
        vessel = _load_vessel()

        duckdb_path = (
            os.environ.get("CROWSNEST_DUCKDB_PATH")
            or _read_duckdb_path_from_profiles()
            or ":memory:"
        )
        dagster_graphql_url = (
            os.environ.get("CROWSNEST_DAGSTER_URL")
            or "http://localhost:3000/graphql"
        )
        dagster_public_url = (
            os.environ.get("CROWSNEST_DAGSTER_PUBLIC_URL")
            or dagster_graphql_url.removesuffix("/graphql")
        )
        # Infer <target_schema>_elementary from profiles.yml; falls back to "elementary"
        elementary_schema = (
            os.environ.get("CROWSNEST_ELEMENTARY_SCHEMA")
            or _infer_elementary_schema()
            or "elementary"
        )
        marimo_url = os.environ.get("CROWSNEST_MARIMO_URL") or "http://127.0.0.1:2718"
        catalog, data, alias = _discover_lake()
        if vessel is not None and vessel.is_valk:
            # db.py attaches the Valk catalog through vessel.py; a lake/ folder that
            # happens to sit in the image must not be picked up instead.
            catalog, data = None, None
            alias = os.environ.get("CROWSNEST_DUCKLAKE_ALIAS") or vessel.valk.catalog_alias

        return cls(
            duckdb_path=duckdb_path,
            dagster_graphql_url=dagster_graphql_url,
            elementary_schema=elementary_schema,
            marimo_url=marimo_url,
            ducklake_catalog_path=catalog,
            ducklake_alias=alias,
            ducklake_data_path=data,
            dagster_public_url=dagster_public_url,
            vessel=vessel,
        )


def get_config() -> CrowsnestConfig:
    global _config
    if _config is None:
        _config = CrowsnestConfig.discover()
    return _config


def reset_config() -> None:
    """Force re-discovery on next get_config() call (useful for testing)."""
    global _config
    _config = None


# ---------------------------------------------------------------------------
# datavloot.yml
# ---------------------------------------------------------------------------

def _load_vessel():
    """The project's vessel, or None when there is no datavloot.yml and no override."""
    try:
        from datavloot_platform.vessel import load_vessel, find_config
    except ImportError:
        return None
    if find_config() is None and not os.environ.get("DATAVLOOT_VESSEL"):
        return None
    try:
        return load_vessel()
    except Exception as exc:  # a broken datavloot.yml must not take the dashboard down
        print(f"  !!  datavloot.yml could not be read ({exc}); assuming the Optimist.")
        return None


def _discover_lake() -> tuple[Optional[str], Optional[str], str]:
    """
    (catalog, data directory, alias) of the lake to serve, or (None, None, alias).

    CROWSNEST_DUCKLAKE_CATALOG_PATH points at a SQLite catalog file; a
    `ducklake:sqlite:` or `sqlite:` prefix is accepted and dropped, since the
    attach adds its own. Its data directory defaults to `data/` next to the
    catalog, as storage.py lays it out. Without the variable, the lake of the
    project in the current directory is used once it exists.
    """
    import os

    from datavloot_platform import storage

    alias = os.environ.get("CROWSNEST_DUCKLAKE_ALIAS")
    configured = os.environ.get("CROWSNEST_DUCKLAKE_CATALOG_PATH")
    if configured:
        for prefix in ("ducklake:", "sqlite:"):
            if configured.startswith(prefix):
                configured = configured[len(prefix):]
        catalog = pathlib.Path(configured).resolve()
        data = os.environ.get("CROWSNEST_DUCKLAKE_DATA_PATH") or str(catalog.parent / "data")
        return str(catalog), str(pathlib.Path(data).resolve()), alias or "lakehouse"

    # An explicit .duckdb file wins over a lake found by looking around.
    if os.environ.get("CROWSNEST_DUCKDB_PATH"):
        return None, None, alias or "lakehouse"

    project = storage.find_project_dir()
    if project is not None and storage.catalog_path(project).is_file():
        return (
            str(storage.catalog_path(project)),
            str(storage.data_path(project)),
            alias or storage.project_name(project),
        )
    return None, None, alias or "lakehouse"


def _read_profiles() -> Optional[dict]:
    if not _HAS_YAML:
        return None
    profiles_path = pathlib.Path.cwd() / "profiles.yml"
    if not profiles_path.exists():
        return None
    try:
        with open(profiles_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _read_duckdb_path_from_profiles() -> Optional[str]:
    profiles = _read_profiles()
    if not isinstance(profiles, dict):
        return None
    for profile_data in profiles.values():
        if not isinstance(profile_data, dict):
            continue
        outputs = profile_data.get("outputs", {})
        if not isinstance(outputs, dict):
            continue
        for output_config in outputs.values():
            if not isinstance(output_config, dict):
                continue
            if output_config.get("type") == "duckdb":
                path = output_config.get("path")
                if path and path != ":memory:":
                    p = pathlib.Path(path)
                    if not p.is_absolute():
                        p = pathlib.Path.cwd() / p
                    return str(p)
    return None


def _infer_elementary_schema() -> Optional[str]:
    """
    Infer the Elementary schema using dbt's default generate_schema_name logic:
    <target_schema>_elementary.

    A project with `schema: noaa` in profiles.yml and `models: elementary: +schema: elementary`
    in dbt_project.yml will have Elementary tables in `noaa_elementary`.

    The prod output wins: it is what Dagster builds, while the default dev output
    writes to dev_elementary. Projects without one use their first duckdb output.
    """
    profiles = _read_profiles()
    if not isinstance(profiles, dict):
        return None
    for profile_data in profiles.values():
        if not isinstance(profile_data, dict):
            continue
        outputs = profile_data.get("outputs", {})
        if not isinstance(outputs, dict):
            continue
        candidates = [outputs.get("prod"), *outputs.values()]
        for output_config in candidates:
            if not isinstance(output_config, dict):
                continue
            if output_config.get("type") == "duckdb":
                schema = output_config.get("schema")
                if schema:
                    return f"{schema}_elementary"
    return None
