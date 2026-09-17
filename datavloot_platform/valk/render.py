"""
Render `deploy/valk/` from datavloot.yml.

The output is a Docker Compose *overlay* on top of SRDP's own
`deploy/docker/docker-compose.yml`, plus the images and config that overlay
references. SRDP's file supplies Traefik, Zitadel, oauth2-proxy, Postgres and the
Dagster process split; the overlay supplies this project's code server, the Crows
Nest, and the domain (SRDP's compose hardcodes `local.dev`).

Everything written here is derived, so it is safe to delete and re-render. The
one exception is `deploy/valk/.env`: it holds generated secrets and the Zitadel
client credentials you paste in by hand, so it is created once and never
overwritten (and is git-ignored).
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import secrets
import string

import yaml

from datavloot_platform import vessel as vessel_mod
from datavloot_platform.vessel import VesselConfig, VesselConfigError

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
VALK_DIRNAME = pathlib.Path("deploy") / "valk"

# Services SRDP publishes on their own hostnames; the Crows Nest is ours.
HOSTS = ("auth", "dagster", "marimo", "quarto", "crowsnest")

# Fallbacks when the running interpreter has no dagster installed (render is
# allowed to run from a bare `pip install datavloot`). Kept in lockstep with the
# `optimist` extra in pyproject.toml.
_FALLBACK_DAGSTER = "1.13.6"
_FALLBACK_DAGSTER_LIB = "0.29.6"


class _Template(string.Template):
    # `$` is Compose's own interpolation syntax, so the templates use `@@name`.
    delimiter = "@@"
    idpattern = r"[a-z][_a-z0-9]*"


@dataclasses.dataclass
class RenderResult:
    valk_dir: pathlib.Path
    written: list[pathlib.Path] = dataclasses.field(default_factory=list)
    skipped: list[pathlib.Path] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def _installed(dist: str, fallback: str) -> str:
    try:
        from importlib.metadata import version
        return version(dist)
    except Exception:
        return fallback


def _module_name(project_dir: pathlib.Path, name: str) -> str:
    """The Dagster code location module, from pyproject's [tool.dagster]."""
    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        try:
            import tomllib  # 3.11+
            module = (tomllib.loads(text).get("tool", {}).get("dagster", {}) or {}).get("module_name")
            if module:
                return str(module)
        except Exception:
            match = re.search(r'module_name\s*=\s*"([^"]+)"', text)
            if match:
                return match.group(1)
    return f"{name}_platform.definitions"


def _datavloot_spec(source: str | None) -> str:
    """
    What the project image pip-installs.

    Default: the datavloot release that rendered the overlay, from PyPI. A git
    source (`git+https://...@branch`) is for running an unreleased toolkit, which
    is exactly the situation while the Valk itself is on a feature branch.
    """
    if source and source.startswith("git+"):
        return f"datavloot[valk] @ {source}"
    if source and source not in ("pypi", ""):
        return f"datavloot[valk]=={source}"
    return f"datavloot[valk]=={_installed('datavloot', '0.1.2')}"


def build_context(config: VesselConfig, *, datavloot_source: str | None = None) -> dict:
    if config.valk is None:
        raise VesselConfigError("render needs `vessel: valk` in datavloot.yml")
    valk = config.valk
    storage = valk.storage
    project_dir = config.project_dir
    valk_dir = project_dir / VALK_DIRNAME
    local_storage = storage.kind == "local"

    return {
        "domain": valk.domain,
        "srdp_repo": valk.srdp_repo,
        "srdp_ref": valk.srdp_ref,
        "project_name": config.name,
        "module_name": _module_name(project_dir, config.name),
        "project_dir": project_dir.as_posix(),
        "valk_dir": valk_dir.as_posix(),
        "catalog_alias": valk.catalog_alias,
        "metadata_schema": valk.metadata_schema,
        "data_path": storage.url,
        "storage_kind": storage.kind,
        "s3_endpoint": storage.endpoint or "",
        "s3_region": storage.region or "",
        "s3_url_style": storage.url_style,
        "default_role": valk.default_role,
        "acme_email": valk.acme_email or "",
        "insecure_tls": "false" if valk.acme_email else "true",
        "dagster_version": _installed("dagster", _FALLBACK_DAGSTER),
        "dagster_lib_version": _installed("dagster-dbt", _FALLBACK_DAGSTER_LIB),
        "datavloot_spec": _datavloot_spec(datavloot_source),
        # Local storage is a named volume shared by the code server and the Crows
        # Nest; S3 needs no volume at all.
        "ducklake_volume_mount": (
            "    volumes:\n      - ducklake-data:/data/ducklake\n" if local_storage else ""
        ),
        "ducklake_volume_def": "volumes:\n  ducklake-data:\n    name: valk-ducklake-data\n" if local_storage else "",
        "hosts_rule": " || ".join(f"Host(`{valk.host(h)}`)" for h in HOSTS),
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, text: str, result: RenderResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes, not write_text: these files run inside Linux containers, and a
    # Windows checkout must not hand them CRLF line endings.
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    result.written.append(path)


def _render_template(name: str, context: dict) -> str:
    source = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    return _Template(source).substitute(context)


def _valk_dbt_output(config: VesselConfig) -> dict:
    """
    The dbt target that writes into the shared DuckLake catalog.

    It is the profile SRDP's own reference project uses (PR #51), with three
    additions: `is_ducklake` so dbt-duckdb emits DuckLake-safe DDL, the metadata
    schema so dbt, dlt and the Crows Nest agree on which catalog they share, and
    an S3 secret when storage is a bucket.
    """
    valk = config.valk
    assert valk is not None
    attach = (
        "ducklake:postgres:"
        "host={{ env_var('DUCKLAKE_PG_HOST', 'localhost') }} "
        "port={{ env_var('DUCKLAKE_PG_PORT', '5432') }} "
        "dbname={{ env_var('DUCKLAKE_PG_DB', 'ducklake') }} "
        "user={{ env_var('DUCKLAKE_PG_USER', 'postgres') }} "
        "password={{ env_var('DUCKLAKE_PG_PASSWORD') }}"
    )
    output: dict = {
        "type": "duckdb",
        "path": ":memory:",
        "schema": config.name,
        "extensions": ["ducklake", "httpfs"],
        "attach": [
            {
                "path": attach,
                "alias": valk.catalog_alias,
                "is_ducklake": True,
                "options": {
                    "data_path": "{{ env_var('DUCKLAKE_DATA_PATH', '%s') }}" % valk.storage.url,
                    "override_data_path": True,
                    "metadata_schema": "{{ env_var('DUCKLAKE_METADATA_SCHEMA', '%s') }}" % valk.metadata_schema,
                },
            }
        ],
    }
    if valk.storage.kind == "s3":
        secret: dict = {
            "type": "s3",
            "key_id": "{{ env_var('DATAVLOOT_S3_KEY_ID') }}",
            "secret": "{{ env_var('DATAVLOOT_S3_SECRET') }}",
            "url_style": valk.storage.url_style,
            "use_ssl": True,
        }
        if valk.storage.endpoint:
            secret["endpoint"] = valk.storage.endpoint
        if valk.storage.region:
            secret["region"] = valk.storage.region
        output["secrets"] = [secret]
    return output


def _update_profiles(config: VesselConfig, result: RenderResult) -> None:
    """Add (or refresh) the `valk` output next to the existing `dev` output."""
    path = config.project_dir / "profiles.yml"
    if not path.is_file():
        result.warnings.append(f"{path} not found; no `valk` dbt target written")
        return
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = doc.get(config.name)
    if not isinstance(profile, dict):
        # Fall back to the first profile in the file rather than guessing a name.
        candidates = [k for k, v in doc.items() if isinstance(v, dict) and "outputs" in v]
        if not candidates:
            result.warnings.append(f"{path} has no profile with outputs; no `valk` target written")
            return
        profile = doc[candidates[0]]
    outputs = profile.setdefault("outputs", {})
    outputs["valk"] = _valk_dbt_output(config)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    result.written.append(path)


def _update_gitignore(config: VesselConfig, result: RenderResult) -> None:
    path = config.project_dir / ".gitignore"
    wanted = ["deploy/valk/.env", ".srdp/"]
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    missing = [w for w in wanted if w not in existing]
    if not missing:
        return
    text = "\n".join(existing + missing) + "\n"
    path.write_text(text, encoding="utf-8")
    result.written.append(path)


def _write_env_once(valk_dir: pathlib.Path, context: dict, result: RenderResult) -> None:
    """
    `.env` is the only rendered file with secrets in it, so it is written once.

    Internal secrets are generated here; the two Zitadel client values stay empty
    until the operator creates the OIDC application (SRDP issue #35 tracks
    automating that).
    """
    env_path = valk_dir / ".env"
    if env_path.exists():
        result.skipped.append(env_path)
        return
    filled = {
        **context,
        "zitadel_masterkey": secrets.token_hex(16),      # 32 chars, as Zitadel requires
        "oidc_cookie_secret": secrets.token_hex(16),     # 32 bytes, one of oauth2-proxy's sizes
        "zitadel_admin_password": "Valk-" + secrets.token_urlsafe(12) + "1!",
    }
    _write(env_path, _render_template("env.tmpl", filled), result)


def _check_project_wiring(config: VesselConfig, result: RenderResult) -> None:
    """
    Projects scaffolded before the Valk existed hardcode the catalog name.

    dbt resolves `{{ ref() }}` and `{{ source() }}` against the target database,
    which for the valk target is an in-memory DuckDB. The templates now carry
    `+database: "{{ env_var('DATAVLOOT_DBT_DATABASE', ...) }}"` so the Compose
    overlay can point them at the attached catalog. Warn if this project does not.
    """
    dbt_project = config.project_dir / "dbt_project.yml"
    if dbt_project.is_file() and "DATAVLOOT_DBT_DATABASE" not in dbt_project.read_text(encoding="utf-8"):
        result.warnings.append(
            "dbt_project.yml has no `+database: \"{{ env_var('DATAVLOOT_DBT_DATABASE', ...) }}\"` "
            "on its models and seeds; on the Valk, dbt would build into the in-memory database "
            "instead of the shared catalog. See docs/valk.md, 'Existing projects'."
        )
    for sources in config.project_dir.glob("models/**/_sources.yml"):
        if "DATAVLOOT_DBT_DATABASE" not in sources.read_text(encoding="utf-8"):
            result.warnings.append(
                f"{sources.relative_to(config.project_dir).as_posix()} has no "
                "`database: \"{{ env_var('DATAVLOOT_DBT_DATABASE', ...) }}\"`; its source tables "
                "will be looked up in the wrong database on the Valk."
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render(config: VesselConfig, *, datavloot_source: str | None = None) -> RenderResult:
    """Write deploy/valk/ for `config`. Idempotent apart from `.env`."""
    context = build_context(config, datavloot_source=datavloot_source)
    valk_dir = config.project_dir / VALK_DIRNAME
    result = RenderResult(valk_dir=valk_dir)

    for template, target in (
        ("docker-compose.valk.yml.tmpl", "docker-compose.valk.yml"),
        ("Dockerfile.tmpl", "Dockerfile"),
        ("Dockerfile.dagster.tmpl", "Dockerfile.dagster"),
        ("entrypoint.sh.tmpl", "entrypoint.sh"),
        ("traefik.yml.tmpl", "traefik.yml"),
        ("env.example.tmpl", ".env.example"),
        ("README.md.tmpl", "README.md"),
        ("dagster.yaml.tmpl", "dagster/dagster.yaml"),
        ("workspace.yaml.tmpl", "dagster/workspace.yaml"),
    ):
        _write(valk_dir / target, _render_template(template, context), result)

    _write_env_once(valk_dir, context, result)
    _update_profiles(config, result)
    _update_gitignore(config, result)
    _check_project_wiring(config, result)
    return result


def srdp_dir(config: VesselConfig) -> pathlib.Path:
    """Where `datavloot valk fetch` checks SRDP out: inside the project, git-ignored."""
    return config.project_dir / ".srdp"


def compose_files(config: VesselConfig, *, prod: bool = False) -> list[pathlib.Path]:
    """SRDP's compose files first, our overlay last, so ours wins on every merge."""
    docker = srdp_dir(config) / "deploy" / "docker"
    files = [docker / "docker-compose.yml", docker / "docker-compose.override.yml"]
    if prod:
        files.append(docker / "docker-compose.prod.yml")
    files.append(config.project_dir / VALK_DIRNAME / "docker-compose.valk.yml")
    return files


__all__ = [
    "HOSTS",
    "RenderResult",
    "VALK_DIRNAME",
    "build_context",
    "compose_files",
    "render",
    "srdp_dir",
    "vessel_mod",
]
