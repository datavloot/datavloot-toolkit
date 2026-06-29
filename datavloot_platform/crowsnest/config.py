"""
Auto-discovers configuration from the project directory where `optimist crowsnest`
is invoked, with environment variable overrides.

Discovery order:
  1. profiles.yml  → DuckDB file path (outputs.dev.path)
  2. Defaults       → Dagster on localhost:3000, Marimo on localhost:2718
  3. Env vars       → CROWSNEST_* overrides
"""

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
    ):
        self.duckdb_path = duckdb_path
        self.dagster_graphql_url = dagster_graphql_url
        self.elementary_schema = elementary_schema
        self.marimo_url = marimo_url
        self.ducklake_catalog_path = ducklake_catalog_path
        self.ducklake_alias = ducklake_alias

    @classmethod
    def discover(cls) -> "CrowsnestConfig":
        import os

        duckdb_path = (
            os.environ.get("CROWSNEST_DUCKDB_PATH")
            or _read_duckdb_path_from_profiles()
            or ":memory:"
        )
        dagster_graphql_url = (
            os.environ.get("CROWSNEST_DAGSTER_URL")
            or "http://localhost:3000/graphql"
        )
        elementary_schema = os.environ.get("CROWSNEST_ELEMENTARY_SCHEMA") or "elementary"
        marimo_url = os.environ.get("CROWSNEST_MARIMO_URL") or "http://localhost:2718"
        ducklake_catalog_path = os.environ.get("CROWSNEST_DUCKLAKE_CATALOG_PATH") or None
        ducklake_alias = os.environ.get("CROWSNEST_DUCKLAKE_ALIAS") or "lakehouse"

        return cls(
            duckdb_path=duckdb_path,
            dagster_graphql_url=dagster_graphql_url,
            elementary_schema=elementary_schema,
            marimo_url=marimo_url,
            ducklake_catalog_path=ducklake_catalog_path,
            ducklake_alias=ducklake_alias,
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


def _read_duckdb_path_from_profiles() -> Optional[str]:
    if not _HAS_YAML:
        return None
    profiles_path = pathlib.Path.cwd() / "profiles.yml"
    if not profiles_path.exists():
        return None
    try:
        with open(profiles_path, encoding="utf-8") as f:
            profiles = yaml.safe_load(f)
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
    except Exception:
        return None
    return None
