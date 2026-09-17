"""
datavloot.yml and the vessel module: the config surface that moves a project
between the Optimist and the Valk. No Docker, no Postgres, no network.
"""

import pathlib

import pytest
import yaml

from datavloot_platform import vessel


VALK_BLOCK = {
    "vessel": "valk",
    "valk": {
        "domain": "valk.example.nl",
        "storage": {"kind": "local"},
    },
}


def _write(project: pathlib.Path, doc: dict) -> pathlib.Path:
    path = project / vessel.CONFIG_FILENAME
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "harbor"
    p.mkdir()
    (p / "dbt_project.yml").write_text("name: harbor\nprofile: harbor\n", encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("DATAVLOOT_VESSEL", "DUCKLAKE_PG_PASSWORD", "DUCKLAKE_DATA_PATH",
                 "DUCKLAKE_METADATA_SCHEMA", "DATAVLOOT_S3_KEY_ID", "DATAVLOOT_S3_SECRET"):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# Loading

def test_no_file_means_optimist(project):
    """Every project that predates datavloot.yml keeps working unchanged."""
    config = vessel.load_vessel(project)
    assert config.vessel == "optimist"
    assert not config.is_valk
    assert config.valk is None
    assert config.name == "harbor"


def test_valk_block_is_parsed_with_defaults(project):
    _write(project, VALK_BLOCK)
    config = vessel.load_vessel(project)

    assert config.is_valk
    valk = config.valk
    assert valk.domain == "valk.example.nl"
    assert valk.host("crowsnest") == "crowsnest.valk.example.nl"
    assert valk.issuer == "https://auth.valk.example.nl"
    assert valk.metadata_schema == "ducklake_harbor", "ADR-0006 style: one metadata schema per project"
    assert valk.storage.kind == "local"
    assert valk.storage.url == "/data/ducklake"
    assert valk.default_role == "reader"
    assert valk.srdp_ref == vessel.SRDP_REF
    assert valk.srdp_repo == vessel.SRDP_REPO


def test_s3_storage_builds_a_bucket_url(project):
    doc = {**VALK_BLOCK, "valk": {**VALK_BLOCK["valk"], "storage": {
        "kind": "s3", "bucket": "acme-lake", "endpoint": "s3.nl-ams.scw.cloud", "region": "nl-ams",
    }}}
    _write(project, doc)
    storage = vessel.load_vessel(project).valk.storage
    assert storage.url == "s3://acme-lake/harbor/", "prefix defaults to the project name"
    assert storage.endpoint == "s3.nl-ams.scw.cloud"


@pytest.mark.parametrize("bad, message", [
    ({"vessel": "frigate"}, "unknown vessel"),
    ({"vessel": "valk"}, "no `valk:` block"),
    ({"vessel": "valk", "valk": {"domain": "https://x.nl"}}, "bare host name"),
    ({"vessel": "valk", "valk": {"domain": "x.nl", "storage": {"kind": "s3"}}}, "bucket, endpoint"),
    ({"vessel": "valk", "valk": {"domain": "x.nl", "storage": {"kind": "tape"}}}, "storage.kind"),
    ({"vessel": "valk", "valk": {"domain": "x.nl", "access": {"default_role": "root"}}}, "default_role"),
])
def test_bad_config_fails_loudly(project, bad, message):
    _write(project, bad)
    with pytest.raises(vessel.VesselConfigError, match=message):
        vessel.load_vessel(project)


def test_env_override_wins_over_the_file(project, monkeypatch):
    """The Compose overlay flips a checked-out project to valk without editing it."""
    _write(project, VALK_BLOCK)
    monkeypatch.setenv("DATAVLOOT_VESSEL", "optimist")
    assert not vessel.load_vessel(project).is_valk


def test_find_config_walks_up(project, monkeypatch):
    _write(project, VALK_BLOCK)
    nested = project / "models" / "business"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert vessel.find_config() == project / vessel.CONFIG_FILENAME
    assert vessel.load_vessel().is_valk


# --------------------------------------------------------------------------
# Runtime

def test_attach_string_uses_srdp_variable_names(monkeypatch):
    monkeypatch.setenv("DUCKLAKE_PG_HOST", "postgres")
    monkeypatch.setenv("DUCKLAKE_PG_PASSWORD", "pw")
    assert vessel.catalog_attach_string() == (
        "ducklake:postgres:host=postgres port=5432 dbname=ducklake user=postgres password=pw"
    )
    assert vessel.catalog_dsn() == "postgres://postgres:pw@postgres:5432/ducklake"


def test_missing_password_is_a_clear_error():
    with pytest.raises(vessel.VesselConfigError, match="DUCKLAKE_PG_PASSWORD"):
        vessel.catalog_attach_string()


def test_s3_secret_only_for_remote_data(project, monkeypatch):
    assert vessel.s3_secret_sql(None) is None, "local data path: no secret"

    doc = {**VALK_BLOCK, "valk": {**VALK_BLOCK["valk"], "storage": {
        "kind": "s3", "bucket": "b", "endpoint": "s3.nl-ams.scw.cloud", "region": "nl-ams",
    }}}
    _write(project, doc)
    config = vessel.load_vessel(project)
    monkeypatch.setenv("DUCKLAKE_DATA_PATH", "s3://b/harbor/")
    monkeypatch.setenv("DATAVLOOT_S3_KEY_ID", "AK")
    monkeypatch.setenv("DATAVLOOT_S3_SECRET", "SK")
    sql = vessel.s3_secret_sql(config)
    assert sql.startswith("CREATE OR REPLACE SECRET")
    assert "ENDPOINT 's3.nl-ams.scw.cloud'" in sql
    assert "REGION 'nl-ams'" in sql
    assert "URL_STYLE 'path'" in sql


class _FakeConn:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql):
        self.statements.append(sql)
        return self


def test_attach_ducklake_pins_data_path_and_metadata_schema(project, monkeypatch):
    """
    dbt, dlt and the Crows Nest must land in the same catalog. The attach carries
    both the data path and the metadata schema, and selects the catalog so
    unqualified names resolve inside it.
    """
    _write(project, VALK_BLOCK)
    config = vessel.load_vessel(project)
    monkeypatch.setenv("DUCKLAKE_PG_PASSWORD", "pw")
    conn = _FakeConn()

    vessel.attach_ducklake(conn, config, read_only=True)

    attach = next(s for s in conn.statements if s.startswith("ATTACH"))
    assert "ducklake:postgres:" in attach
    assert "DATA_PATH '/data/ducklake'" in attach
    assert "METADATA_SCHEMA 'ducklake_harbor'" in attach
    assert "READ_ONLY" in attach
    assert conn.statements[-1] == "USE ducklake"
    assert not any("httpfs" in s for s in conn.statements), "local storage needs no httpfs"


def test_attach_ducklake_loads_httpfs_for_s3(project, monkeypatch):
    doc = {**VALK_BLOCK, "valk": {**VALK_BLOCK["valk"], "storage": {
        "kind": "s3", "bucket": "b", "endpoint": "s3.nl-ams.scw.cloud",
    }}}
    _write(project, doc)
    config = vessel.load_vessel(project)
    monkeypatch.setenv("DUCKLAKE_PG_PASSWORD", "pw")
    monkeypatch.setenv("DUCKLAKE_DATA_PATH", "s3://b/harbor/")
    monkeypatch.setenv("DATAVLOOT_S3_KEY_ID", "AK")
    monkeypatch.setenv("DATAVLOOT_S3_SECRET", "SK")
    conn = _FakeConn()

    vessel.attach_ducklake(conn, config)

    assert "LOAD httpfs" in conn.statements
    assert any(s.startswith("CREATE OR REPLACE SECRET") for s in conn.statements)
    assert any("DATA_PATH 's3://b/harbor/'" in s for s in conn.statements)


def test_dlt_destination_follows_the_vessel(project, monkeypatch):
    pytest.importorskip("dlt", reason="dlt is not installed")

    optimist = vessel.dlt_destination(project, project / "harbor.duckdb")
    assert optimist.destination_type.endswith("duckdb")

    _write(project, VALK_BLOCK)
    monkeypatch.setenv("DUCKLAKE_PG_PASSWORD", "pw")
    monkeypatch.setenv("DUCKLAKE_DATA_PATH", str(project / "lake"))
    valk = vessel.dlt_destination(project, project / "harbor.duckdb")
    assert valk.destination_type.endswith("ducklake")
    creds = valk.config_params["credentials"]
    assert creds.metadata_schema == "ducklake_harbor", "dlt must write where dbt reads"
    assert creds.ducklake_name == "ducklake"
