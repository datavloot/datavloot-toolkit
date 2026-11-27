from datetime import date
from functools import lru_cache
from pathlib import Path

import dlt
from dlt.sources.helpers import requests as dlt_requests
from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    DefaultScheduleStatus,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets

from datavloot_platform import storage

from . import github

PROJECT_DIR = Path(__file__).parent.parent  # github/

# Every asset that writes to the lake runs in this pool. dagster.yaml limits each
# pool to one at a time, because the lake takes one commit at a time.
LAKE_POOL = "lake"

# Dagster is the only production writer: it builds the prod target, while a
# plain `dbt run` builds dev (see profiles.yml). The dbt resource inherits it.
# install_deps=False: under `datavloot start`, prepare_if_dev would otherwise run
# `dbt deps` on every code load, which first deletes dbt_packages/. When the code
# server and a run load at once, that fails on Windows (WinError 32) and every
# run fails with it. After changing packages.yml, run `uv run dbt deps`.
github_dbt_project = DbtProject(project_dir=PROJECT_DIR, target="prod", install_deps=False)
github_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business); a package's assets by package."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        # By folder, Elementary's models would land in one group per subfolder.
        package = dbt_resource_props.get("package_name")
        if package and package != github_dbt_project.name:
            return package
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


class GitHubDltTranslator(DagsterDltTranslator):
    # Prefix keys with "github" to match the dbt source translation and wire the dependency edge.
    def get_asset_key(self, resource) -> AssetKey:
        return AssetKey(["github", resource.name])


# ---------------------------------------------------------------------------
# GitHub ingestion: the user's own account once connected, the sample before
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _client():
    # Made when a run first reads from it, not when Dagster loads this module.
    return github.client(dlt_requests)


@lru_cache(maxsize=1)
def _repositories() -> list[dict]:
    return github.own_repositories(_client())


def _resource(table: str, rows, write_disposition: str, primary_key):
    """A dlt resource for one table, with all its columns declared, that only calls `rows()` once read."""
    keys = [primary_key] if isinstance(primary_key, str) else primary_key

    def generate():
        # Creates the table from the declared columns, also when `rows()` yields nothing.
        yield dlt.mark.materialize_table_schema()
        yield from rows()

    columns = {name: {"data_type": data_type, "nullable": name not in keys}
               for name, data_type in github.TABLES[table].items()}
    return dlt.resource(generate(), name=table, write_disposition=write_disposition,
                        primary_key=primary_key, columns=columns)


@dlt.source(name="github")
def github_source():
    # Decided from .env alone, so without a network call. Everything is
    # replaced on every run except commits, which merge on their sha: a
    # repository deleted on GitHub keeps its commits here, as a record of the
    # work. When an account is connected later, the sample rows left in that
    # table are filtered out by the staging models (macros/).
    sample = not github.connected()
    today = date.today()
    return [
        _resource("profile", lambda: github.profile_rows(_client()),
                  "replace", "login"),
        _resource("repositories", lambda: github.repository_rows(_client(), _repositories()),
                  "replace", "repository_id"),
        _resource("repository_languages", lambda: github.language_rows(_client(), _repositories()),
                  "replace", ["repository_id", "language"]),
        _resource("commits", lambda: github.commit_rows(_client(), _repositories()),
                  "replace" if sample else "merge", "sha"),
        _resource("contribution_days", lambda: github.contribution_day_rows(
                         _client(), github.calendar_start(_client(), today), today),
                  "replace", "contribution_date"),
    ]


@dlt_assets(
    dlt_source=github_source(),
    dlt_pipeline=dlt.pipeline(
        pipeline_name="github",
        dataset_name="source",
        destination=storage.dlt_destination(PROJECT_DIR),
    ),
    group_name="github_ingest",
    name="github",
    dagster_dlt_translator=GitHubDltTranslator(),
    pool=LAKE_POOL,
)
def github_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    if not github.connected():
        context.log.info(
            "No GitHub account connected: loading the sample developer. To load your own, run "
            "`uv run python -m github_platform.connect` (README: 'Use your own GitHub data')."
        )
    yield from dlt.run(context=context)


# ---------------------------------------------------------------------------
# dbt: transforms the GitHub tables into dims and facts
# ---------------------------------------------------------------------------


@dbt_assets(
    manifest=github_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
    pool=LAKE_POOL,
)
def github_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------------------
# Schedule: every morning, once an account is connected
# ---------------------------------------------------------------------------

github_refresh = define_asset_job(
    "github_refresh",
    selection=AssetSelection.groups("github_ingest").downstream(),
    description="Load the latest repositories, commits and contributions from GitHub and rebuild the models.",
)

github_refresh_schedule = ScheduleDefinition(
    name="github_refresh_daily",
    job=github_refresh,
    cron_schedule="0 7 * * *",
    execution_timezone="Europe/Amsterdam",
    default_status=DefaultScheduleStatus.RUNNING if github.connected() else DefaultScheduleStatus.STOPPED,
)
