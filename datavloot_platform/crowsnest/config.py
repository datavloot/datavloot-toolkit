"""
Auto-discovers configuration from the project directory where `datavloot launch`
is invoked, with environment variable overrides.

Discovery order:
  1. datavloot.yml  → which vessel (Optimist: a DuckDB file; Valk: the shared DuckLake
                      catalog described by the DUCKLAKE_* environment, see vessel.py)
  2. profiles.yml   → DuckDB file path (outputs.<target>.path) and target schema, or a
                      DuckLake `attach:` entry, when the dbt target already points at one
  3. Defaults       → Dagster on localhost:3000, Marimo on localhost:2718
  4. Env vars       → CROWSNEST_* overrides

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
import re
from typing import Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


_config: Optional["CrowsnestConfig"] = None

# `{{ env_var('NAME') }}` / `{{ env_var('NAME', 'default') }}` as dbt writes them in
# profiles.yml. Only this one function is rendered; anything else is left as is.
_ENV_VAR_JINJA = re.compile(
    r"\{\{\s*env_var\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]*)['\"]\s*)?\)\s*\}\}"
)


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
        ducklake_metadata_schema: Optional[str] = None,
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
        self.ducklake_metadata_schema = ducklake_metadata_schema
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
            return f"DuckLake catalog {_redact(self.ducklake_catalog_path)}"
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

        attach = _read_ducklake_attach_from_profiles()
        ducklake_catalog_path = os.environ.get("CROWSNEST_DUCKLAKE_CATALOG_PATH") or attach.get("path")
        ducklake_alias = os.environ.get("CROWSNEST_DUCKLAKE_ALIAS") or attach.get("alias") or "lakehouse"
        ducklake_data_path = os.environ.get("CROWSNEST_DUCKLAKE_DATA_PATH") or attach.get("data_path")
        ducklake_metadata_schema = (
            os.environ.get("CROWSNEST_DUCKLAKE_METADATA_SCHEMA") or attach.get("metadata_schema")
        )
        if vessel is not None and vessel.is_valk:
            ducklake_alias = os.environ.get("CROWSNEST_DUCKLAKE_ALIAS") or vessel.valk.catalog_alias

        return cls(
            duckdb_path=duckdb_path,
            dagster_graphql_url=dagster_graphql_url,
            elementary_schema=elementary_schema,
            marimo_url=marimo_url,
            ducklake_catalog_path=ducklake_catalog_path,
            ducklake_alias=ducklake_alias,
            ducklake_data_path=ducklake_data_path,
            ducklake_metadata_schema=ducklake_metadata_schema,
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


# ---------------------------------------------------------------------------
# profiles.yml
# ---------------------------------------------------------------------------

def _redact(text: str) -> str:
    return re.sub(r"password=\S+", "password=***", text)


def render_env_var_jinja(text: str) -> str:
    """Resolve dbt's `{{ env_var(...) }}` calls against the current environment."""
    def _sub(match: "re.Match[str]") -> str:
        name, default = match.group(1), match.group(2)
        value = os.environ.get(name)
        if value is None:
            value = default if default is not None else ""
        return value
    return _ENV_VAR_JINJA.sub(_sub, text)


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


def _selected_outputs():
    """
    Yield the duckdb output dbt would actually use for each profile.

    dbt picks `DBT_TARGET` if set, else the profile's `target:` key. Iterating
    every output instead (the old behaviour) made the Crows Nest read whichever
    target happened to come first, which is wrong the moment a `valk` output sits
    next to `dev`.
    """
    profiles = _read_profiles()
    if not isinstance(profiles, dict):
        return
    for profile_data in profiles.values():
        if not isinstance(profile_data, dict):
            continue
        outputs = profile_data.get("outputs", {})
        if not isinstance(outputs, dict):
            continue
        target = os.environ.get("DBT_TARGET") or profile_data.get("target")
        selected = outputs.get(target) if target else None
        candidates = [selected] if isinstance(selected, dict) else list(outputs.values())
        for output_config in candidates:
            if isinstance(output_config, dict) and output_config.get("type") == "duckdb":
                yield output_config


def _read_duckdb_path_from_profiles() -> Optional[str]:
    for output_config in _selected_outputs():
        path = output_config.get("path")
        if path and path != ":memory:":
            p = pathlib.Path(path)
            if not p.is_absolute():
                p = pathlib.Path.cwd() / p
            return str(p)
    return None


def _read_ducklake_attach_from_profiles() -> dict:
    """
    A DuckLake `attach:` entry from the selected dbt target, rendered.

    Returns {} when there is none. When there is one, the Crows Nest reads the same
    catalog dbt writes to without any CROWSNEST_DUCKLAKE_* variable being set.
    """
    for output_config in _selected_outputs():
        for entry in output_config.get("attach") or []:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "")
            if not path.startswith("ducklake:") and entry.get("type") != "ducklake" and not entry.get("is_ducklake"):
                continue
            options = entry.get("options") or {}
            return {
                "path": render_env_var_jinja(path),
                "alias": entry.get("alias"),
                "data_path": render_env_var_jinja(str(options["data_path"])) if options.get("data_path") else None,
                "metadata_schema": (
                    render_env_var_jinja(str(options["metadata_schema"])) if options.get("metadata_schema") else None
                ),
            }
    return {}


def _infer_elementary_schema() -> Optional[str]:
    """
    Infer the Elementary schema using dbt's default generate_schema_name logic:
    <target_schema>_elementary.

    A project with `schema: noaa` in profiles.yml and `models: elementary: +schema: elementary`
    in dbt_project.yml will have Elementary tables in `noaa_elementary`.
    """
    for output_config in _selected_outputs():
        schema = output_config.get("schema")
        if schema:
            return f"{schema}_elementary"
    return None
