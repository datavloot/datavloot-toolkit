"""
`datavloot valk render`: datavloot.yml in, deploy/valk/ out. No Docker needed.

The overlay is layered on SRDP's compose file at a pinned commit, so the
assertions here are about the contract with that file (service names, label
keys, hosts) and about not leaking secrets into anything that gets committed.
"""

import pathlib

import pytest
import yaml

from datavloot_platform import vessel
from datavloot_platform.valk import render as render_mod


def _valk(scaffold: pathlib.Path, **storage) -> vessel.VesselConfig:
    doc = {
        "vessel": "valk",
        "valk": {
            "domain": "probe.valk.test",
            "storage": storage or {"kind": "local"},
        },
    }
    (scaffold / "datavloot.yml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return vessel.load_vessel(scaffold)


@pytest.fixture
def rendered(scaffold: pathlib.Path):
    config = _valk(scaffold)
    result = render_mod.render(config)
    return config, result


def _compose(result) -> dict:
    return yaml.safe_load((result.valk_dir / "docker-compose.valk.yml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------

def test_render_writes_the_whole_deploy_dir(rendered):
    _, result = rendered
    names = {p.relative_to(result.valk_dir).as_posix() for p in result.written if result.valk_dir in p.parents}
    assert {
        "docker-compose.valk.yml", "Dockerfile", "Dockerfile.dagster", "entrypoint.sh",
        "traefik.yml", ".env", ".env.example", "README.md",
        "dagster/dagster.yaml", "dagster/workspace.yaml",
    } <= names
    assert result.warnings == [], "a fresh scaffold must not trip the wiring checks"


def test_overlay_matches_srdp_service_names(rendered):
    """The overlay is only an overlay if its keys exist in SRDP's compose."""
    _, result = rendered
    services = _compose(result)["services"]
    # Names from srdp deploy/docker/docker-compose.yml at the pinned commit.
    for name in ("traefik", "zitadel", "zitadel-init", "zitadel-login", "oauth2-proxy",
                 "dagster-webserver", "dagster-daemon", "dagster-code", "marimo", "quarto"):
        assert name in services, f"SRDP service {name} missing from the overlay"
    assert "crowsnest" in services, "our own addition"


def test_every_host_carries_the_domain(rendered):
    config, result = rendered
    text = (result.valk_dir / "docker-compose.valk.yml").read_text(encoding="utf-8")
    for host in render_mod.HOSTS:
        assert f"{host}.probe.valk.test" in text
    assert "local.dev" not in text, "SRDP's hardcoded domain must be fully shadowed"

    traefik = (result.valk_dir / "traefik.yml").read_text(encoding="utf-8")
    assert "auth.probe.valk.test" in traefik and "local.dev" not in traefik


def test_oauth2_proxy_forwards_the_access_token(rendered):
    """
    SRDP forwards only user and email headers. The Crows Nest validates the token
    itself (ADR-0008: never trust headers), so the token must reach it.
    """
    _, result = rendered
    labels = _compose(result)["services"]["oauth2-proxy"]["labels"]
    joined = "\n".join(labels)
    assert "X-Auth-Request-Access-Token" in joined
    assert "Host(`crowsnest.probe.valk.test`)" in joined, "crowsnest must be in the /oauth2 router rule"
    command = "\n".join(_compose(result)["services"]["oauth2-proxy"]["command"])
    assert "--pass-access-token=true" in command
    assert "roles" in command, "Zitadel only asserts roles when the scope asks for them"


def test_code_server_and_crowsnest_share_the_catalog_env(rendered):
    _, result = rendered
    services = _compose(result)["services"]
    code, nest = services["dagster-code"]["environment"], services["crowsnest"]["environment"]
    for key in ("DATAVLOOT_VESSEL", "DUCKLAKE_PG_HOST", "DUCKLAKE_DATA_PATH",
                "DUCKLAKE_METADATA_SCHEMA", "DBT_TARGET", "DATAVLOOT_DBT_DATABASE"):
        assert code[key] == nest[key], key
    assert code["DATAVLOOT_VESSEL"] == "valk"
    assert code["DUCKLAKE_METADATA_SCHEMA"] == "ducklake_probe"
    assert code["DATAVLOOT_DBT_DATABASE"] == "ducklake"
    assert nest["CROWSNEST_OIDC_ISSUER"] == "https://auth.probe.valk.test"
    assert nest["CROWSNEST_DAGSTER_URL"] == "http://dagster-webserver:3000/graphql"


def test_local_storage_is_a_shared_volume(rendered):
    _, result = rendered
    doc = _compose(result)
    assert "ducklake-data:/data/ducklake" in doc["services"]["dagster-code"]["volumes"]
    assert "ducklake-data:/data/ducklake" in doc["services"]["crowsnest"]["volumes"]
    assert "ducklake-data" in doc["volumes"]


def test_s3_storage_has_no_volume_and_a_dbt_secret(scaffold):
    config = _valk(scaffold, kind="s3", bucket="acme-lake", endpoint="s3.nl-ams.scw.cloud", region="nl-ams")
    result = render_mod.render(config)
    doc = _compose(result)
    assert "volumes" not in doc["services"]["dagster-code"]
    assert "volumes" not in doc
    assert doc["services"]["dagster-code"]["environment"]["DUCKLAKE_DATA_PATH"] == "s3://acme-lake/probe/"

    profiles = yaml.safe_load((scaffold / "profiles.yml").read_text(encoding="utf-8"))
    valk = profiles["probe"]["outputs"]["valk"]
    assert valk["secrets"][0]["type"] == "s3"
    assert valk["secrets"][0]["endpoint"] == "s3.nl-ams.scw.cloud"
    assert "env_var('DATAVLOOT_S3_SECRET')" in valk["secrets"][0]["secret"], "secret by env var, not by value"


def test_profiles_gain_a_valk_target_and_keep_dev(rendered):
    config, _ = rendered
    profiles = yaml.safe_load((config.project_dir / "profiles.yml").read_text(encoding="utf-8"))
    outputs = profiles["probe"]["outputs"]
    assert outputs["dev"]["path"] == "probe.duckdb", "the Optimist target is untouched"
    valk = outputs["valk"]
    assert valk["path"] == ":memory:"
    attach = valk["attach"][0]
    assert attach["path"].startswith("ducklake:postgres:")
    assert "env_var('DUCKLAKE_PG_PASSWORD')" in attach["path"]
    assert attach["is_ducklake"] is True
    assert attach["alias"] == "ducklake"
    assert "override_data_path" in attach["options"]
    assert "ducklake_probe" in attach["options"]["metadata_schema"]


def test_env_is_generated_once_and_never_committed(rendered):
    config, result = rendered
    env = (result.valk_dir / ".env").read_text(encoding="utf-8")
    masterkey = next(l for l in env.splitlines() if l.startswith("ZITADEL_MASTERKEY=")).split("=", 1)[1]
    assert len(masterkey) == 32, "Zitadel requires exactly 32 characters"
    assert "OIDC_CLIENT_ID=\n" in env, "the Zitadel client is a manual step; left empty"

    second = render_mod.render(config)
    assert (result.valk_dir / ".env") in second.skipped
    assert (result.valk_dir / ".env").read_text(encoding="utf-8") == env

    example = (result.valk_dir / ".env.example").read_text(encoding="utf-8")
    assert masterkey not in example

    gitignore = (config.project_dir / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "deploy/valk/.env" in gitignore and ".srdp/" in gitignore


def test_container_files_have_unix_line_endings(rendered):
    """Rendered on Windows, executed in Linux containers: no CRLF, ever."""
    _, result = rendered
    for name in ("entrypoint.sh", "Dockerfile", "Dockerfile.dagster", "docker-compose.valk.yml"):
        assert b"\r" not in (result.valk_dir / name).read_bytes(), name


def test_image_installs_the_toolkit_and_the_code_location(rendered):
    _, result = rendered
    dockerfile = (result.valk_dir / "Dockerfile").read_text(encoding="utf-8")
    assert 'pip install --no-cache-dir "datavloot[valk]==' in dockerfile
    assert "probe_platform.definitions" in dockerfile, "module name comes from pyproject [tool.dagster]"
    workspace = yaml.safe_load((result.valk_dir / "dagster/workspace.yaml").read_text(encoding="utf-8"))
    assert workspace["load_from"][0]["grpc_server"]["host"] == "srdp-dagster-code"


def test_git_source_for_an_unreleased_toolkit(scaffold):
    config = _valk(scaffold)
    result = render_mod.render(config, datavloot_source="git+https://gitlab.com/datavloot/datavloot-toolkit.git@feature/evka_valk_vessel")
    dockerfile = (result.valk_dir / "Dockerfile").read_text(encoding="utf-8")
    assert "datavloot[valk] @ git+https://gitlab.com/datavloot/datavloot-toolkit.git@feature/evka_valk_vessel" in dockerfile


def test_compose_files_put_our_overlay_last(rendered):
    config, _ = rendered
    files = render_mod.compose_files(config, prod=True)
    assert files[0].name == "docker-compose.yml" and ".srdp" in files[0].parts
    assert files[-2].name == "docker-compose.prod.yml"
    assert files[-1].name == "docker-compose.valk.yml", "later files win on merge"


def test_render_refuses_an_optimist_project(scaffold):
    config = vessel.load_vessel(scaffold)
    with pytest.raises(vessel.VesselConfigError):
        render_mod.render(config)


def test_legacy_project_without_database_config_is_warned(scaffold):
    """A project scaffolded before the Valk would silently build into :memory:."""
    dbt_project = scaffold / "dbt_project.yml"
    dbt_project.write_text(dbt_project.read_text(encoding="utf-8").replace("DATAVLOOT_DBT_DATABASE", "X"), encoding="utf-8")
    result = render_mod.render(_valk(scaffold))
    assert any("dbt_project.yml" in w for w in result.warnings)
