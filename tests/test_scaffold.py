"""
Fast checks on the scaffold template. No dbt, no network.

Every assertion here is a regression guard for something that actually shipped
broken -- see the docstrings.
"""

import pathlib

import pytest
import yaml


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


def test_profile_writes_to_a_file_not_memory(scaffold: pathlib.Path):
    """
    The scaffold must persist to disk.

    It shipped with `path: ":memory:"`, so `dbt run` reported tables built and
    left nothing behind -- a silent failure, and worse than the parse error it
    replaced.
    """
    profile = yaml.safe_load((scaffold / "profiles.yml").read_text(encoding="utf-8"))
    path = profile["probe"]["outputs"]["dev"]["path"]

    assert path != ":memory:", "scaffold would persist nothing"
    assert path == "probe.duckdb"


def test_every_model_layer_sets_a_custom_schema(scaffold: pathlib.Path):
    """
    No layer may fall back to the bare target schema.

    The target schema is named after the project, and so is the DuckDB file, so
    the catalog and that schema collide. DuckDB then refuses two-part names:
    `Ambiguous reference to catalog or schema "probe"`. dbt is unaffected (it
    emits three-part names); it breaks what a person types.
    """
    project = yaml.safe_load((scaffold / "dbt_project.yml").read_text(encoding="utf-8"))
    # `+database` and friends are project-level configs, not layers.
    layers = {k: v for k, v in project["models"]["probe"].items() if not k.startswith("+")}

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
