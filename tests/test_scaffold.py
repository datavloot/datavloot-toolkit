"""
Fast checks on the scaffold template. No dbt, no network.

Every assertion here is a regression guard for something that actually shipped
broken -- see the docstrings.
"""

import ast
import pathlib

import pytest
import yaml

from datavloot_platform import cli

TEMPLATES = {"scaffold": "probe_platform", "demo": "noaa_platform"}


def test_placeholders_are_substituted(scaffold: pathlib.Path):
    """No <project_name> or project_platform token survives `datavloot new`."""
    leftovers = []
    for f in scaffold.rglob("*"):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if "<project_name>" in text or "project_platform" in text:
            leftovers.append(f.relative_to(scaffold).as_posix())
    assert leftovers == [], f"unsubstituted placeholders in: {leftovers}"

    assert (scaffold / "probe_platform").is_dir(), "module dir was not renamed"


@pytest.mark.parametrize("target", ["dev", "prod"])
def test_profile_writes_to_the_lake_not_memory(scaffold: pathlib.Path, target: str):
    """
    The scaffold must persist to disk.

    It once shipped with `path: ":memory:"` and nothing attached, so `dbt run`
    reported tables built and left nothing behind -- a silent failure. The
    session database is still in memory, so what persists is the attached lake:
    dbt's `database` has to be that attach, or every model lands in memory again.
    """
    profile = yaml.safe_load((scaffold / "profiles.yml").read_text(encoding="utf-8"))
    output = profile["probe"]["outputs"][target]
    attaches = {a["alias"]: a for a in output.get("attach", [])}

    assert output["database"] in attaches, "dbt writes to the in-memory session, not the lake"
    lake = attaches[output["database"]]
    assert lake["path"].startswith("ducklake:sqlite:") and lake["path"].endswith("/catalog.sqlite")

    # The two options the lake does not work without (see storage.py): WAL, or
    # readers and writers lock each other out; the override, or a relative data
    # path follows the current directory.
    options = lake["options"]
    assert options["meta_journal_mode"] == "WAL"
    assert options["override_data_path"] is True


def test_dbt_by_hand_never_writes_to_production(scaffold: pathlib.Path):
    """
    A plain `dbt run` builds dev, into schemas apart from production's.

    The scaffold had a single `dev` target that wrote to the production
    schemas, so any manual run overwrote what Dagster had built. dbt prefixes
    every custom schema with the target schema, so distinct target schemas keep
    dev_business and probe_business apart -- in the same lake, which prod and
    dev both attach.
    """
    profile = yaml.safe_load((scaffold / "profiles.yml").read_text(encoding="utf-8"))["probe"]
    dev, prod = profile["outputs"]["dev"], profile["outputs"]["prod"]

    assert profile["target"] == "dev", "the default target must be dev, not production"
    assert prod["schema"] == "probe", "production schemas would no longer be <project>_*"
    assert dev["schema"] != prod["schema"]
    assert not dev["schema"].startswith(f"{prod['schema']}_"), (
        f"dev's schemas ({dev['schema']}_business) would read as production's"
    )
    assert dev["attach"] == prod["attach"] and dev["database"] == prod["database"], (
        "dev and prod must attach the same lake, or dev cannot read production sources"
    )


def test_crowsnest_reports_production_quality(scaffold: pathlib.Path, monkeypatch):
    """The Crows Nest shows Elementary results from prod, not from the default dev target."""
    from datavloot_platform.crowsnest import config

    monkeypatch.chdir(scaffold)
    assert config._infer_elementary_schema() == "probe_elementary"


def _platform_dir(template: str, scaffold: pathlib.Path) -> pathlib.Path:
    if template == "scaffold":
        return scaffold / TEMPLATES[template]
    return cli.TEMPLATES_DIR / template / TEMPLATES[template]


def _keyword(call: ast.Call, name: str):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


@pytest.mark.parametrize("template", TEMPLATES)
def test_dagster_builds_the_prod_target(scaffold: pathlib.Path, template: str):
    """Dagster is the production writer, so its dbt project uses prod, not the default dev."""
    tree = ast.parse((_platform_dir(template, scaffold) / "assets.py").read_text(encoding="utf-8"))
    projects = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "DbtProject"
    ]

    assert projects, "no DbtProject in assets.py"
    for project in projects:
        target = _keyword(project, "target")
        assert isinstance(target, ast.Constant) and target.value == "prod", (
            "DbtProject has no target='prod'; Dagster would build the dev schemas"
        )


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_writing_asset_waits_its_turn(scaffold: pathlib.Path, template: str):
    """
    Writers to the lake take turns, enforced by Dagster.

    The lake accepts one commit at a time and refuses a second with "database
    is locked" instead of waiting. dagster.yaml limits each pool to one running
    asset, across runs and within a run; that only helps the assets in a pool.
    """
    instance = yaml.safe_load(
        (cli.TEMPLATES_DIR / template / "dagster.yaml").read_text(encoding="utf-8")
    )
    pools = instance["concurrency"]["pools"]
    assert pools["default_limit"] == 1
    assert pools["granularity"] == "op", "with run granularity, steps within one run still overlap"

    # Ops too: lake maintenance commits to the lake like any asset.
    decorators = [
        dec
        for module in sorted(_platform_dir(template, scaffold).glob("*.py"))
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
        for dec in node.decorator_list
        if getattr(dec.func if isinstance(dec, ast.Call) else dec, "id", None)
        in {"asset", "multi_asset", "dbt_assets", "dlt_assets", "op"}
    ]

    assert decorators, "no assets found in the platform module"
    outside = [
        ast.unparse(dec) for dec in decorators
        if not isinstance(dec, ast.Call)
        or not (isinstance(_keyword(dec, "pool"), ast.Name) and _keyword(dec, "pool").id == "LAKE_POOL")
    ]
    assert outside == [], f"assets that write outside the lake pool: {outside}"


def test_every_model_layer_sets_a_custom_schema(scaffold: pathlib.Path):
    """
    No layer may fall back to the bare target schema.

    The target schema is named after the project, and so is the catalog the
    lake is attached as, so the catalog and that schema collide. DuckDB then refuses two-part names:
    `Ambiguous reference to catalog or schema "probe"`. dbt is unaffected (it
    emits three-part names); it breaks what a person types.
    """
    project = yaml.safe_load((scaffold / "dbt_project.yml").read_text(encoding="utf-8"))
    layers = project["models"]["probe"]

    missing = [name for name, cfg in layers.items() if "+schema" not in cfg]
    assert missing == [], f"layers with no +schema, will collide with the catalog: {missing}"


@pytest.mark.parametrize(
    "relpath",
    [
        "models/source/_schema.yml",
        "models/business/facts/_fct_configs.yml",
        "models/business/datasets/_dataset_configs.yml",
        "models/business/dimensions/_dim_configs.yml",
    ],
)
def test_config_templates_are_valid_yaml(scaffold: pathlib.Path, relpath: str):
    """
    Every shipped config parses, and an empty `models:` is an explicit list.

    A bare `models:` with only commented examples under it parses as null, which
    dbt rejects. The fix was `models: []` -- this keeps it that way, and keeps
    the annotation telling the reader to remove the [] before adding an entry.
    """
    text = (scaffold / relpath).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)

    assert doc is not None, f"{relpath} parses as null"
    assert "models" in doc, f"{relpath} has no models key"
    assert doc["models"] is not None, f"{relpath} has a null models key; use [] instead"

    if doc["models"] == []:
        assert "models: []" in text
        assert "remove the []" in text, (
            f"{relpath} has an empty models list with no note telling the reader "
            "to remove it before uncommenting the example below"
        )


def test_no_placeholder_model_is_declared(scaffold: pathlib.Path):
    """
    Templates must not declare models that do not exist.

    `_schema.yml` shipped a literal stg_<source_name>__<table_name> entry with
    tests attached, so dbt registered two tests against a missing model and a
    fresh project's first parse emitted three warnings.
    """
    doc = yaml.safe_load((scaffold / "models/source/_schema.yml").read_text(encoding="utf-8"))
    declared = {m["name"] for m in (doc.get("models") or [])}

    sql_models = {p.stem for p in (scaffold / "models").rglob("*.sql")}
    orphans = declared - sql_models
    assert orphans == set(), f"declared in YAML but no .sql file exists: {orphans}"


def test_no_placeholder_source_is_declared(scaffold: pathlib.Path):
    """
    Templates must not declare sources that do not exist.

    `_sources.yml` shipped an active <source_name>.<table_name> with unique and
    not_null tests. `dbt run` skips tests, so it passed; `dbt build` -- which is
    what Dagster runs on the first materialization -- executed them and failed
    on `select <primary_key_column>`. On Windows it failed even earlier: the
    test names contain < and >, which are not allowed in file names.
    """
    text = (scaffold / "models/source/_sources.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)

    assert doc["sources"] == [], f"_sources.yml declares sources: {doc['sources']}"
    assert "remove the []" in text, (
        "_sources.yml has an empty sources list with no note telling the reader "
        "to remove it before uncommenting the example below"
    )
