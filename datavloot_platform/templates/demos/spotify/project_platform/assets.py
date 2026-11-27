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

from . import spotify

PROJECT_DIR = Path(__file__).parent.parent  # spotify/

# Every asset that writes to the lake runs in this pool. dagster.yaml limits each
# pool to one at a time, because the lake takes one commit at a time.
LAKE_POOL = "lake"

# Dagster is the only production writer: it builds the prod target, while a
# plain `dbt run` builds dev (see profiles.yml). The dbt resource inherits it.
# install_deps=False: under `datavloot start`, prepare_if_dev would otherwise run
# `dbt deps` on every code load, which first deletes dbt_packages/. When the code
# server and a run load at once, that fails on Windows (WinError 32) and every
# run fails with it. After changing packages.yml, run `uv run dbt deps`.
spotify_dbt_project = DbtProject(project_dir=PROJECT_DIR, target="prod", install_deps=False)
spotify_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business); a package's assets by package."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        # By folder, Elementary's models would land in one group per subfolder.
        package = dbt_resource_props.get("package_name")
        if package and package != spotify_dbt_project.name:
            return package
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


class SpotifyDltTranslator(DagsterDltTranslator):
    # Prefix keys with "spotify" to match the dbt source translation and wire the dependency edge.
    def get_asset_key(self, resource) -> AssetKey:
        return AssetKey(["spotify", resource.name])


# ---------------------------------------------------------------------------
# Spotify ingestion: the user's own account once connected, the sample before
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _client():
    # Made when a run first reads from it, not when Dagster loads this module:
    # loading the code must not call Spotify (or refresh a token) every time.
    return spotify.client(dlt_requests)


@lru_cache(maxsize=1)
def _user_id() -> str:
    return spotify.account(_client())[0]["user_id"]


def _lazy(rows):
    """A generator that only calls `rows()` once dlt starts reading it."""
    yield from rows()


@dlt.source(name="spotify")
def spotify_source():
    # Decided from .env alone, so without a network call. The sample is made
    # afresh on every run, so its tables are replaced; a real account's plays
    # and rankings are kept and added to, because Spotify only gives the
    # latest. When an account is connected later, the sample rows left in
    # those two tables are filtered out by the staging models (macros/).
    sample = not spotify.connected()
    keep = "replace" if sample else "merge"
    today = date.today()
    return [
        dlt.resource(_lazy(lambda: spotify.account(_client())), name="account",
                     write_disposition="replace", primary_key="user_id"),
        dlt.resource(_lazy(lambda: spotify.recently_played(_client())), name="recently_played",
                     write_disposition=keep, primary_key="played_at"),
        dlt.resource(_lazy(lambda: spotify.top_tracks(_client(), today)), name="top_tracks",
                     write_disposition=keep, primary_key=["snapshot_date", "time_range", "rank"]),
        dlt.resource(_lazy(lambda: spotify.top_artists(_client(), today)), name="top_artists",
                     write_disposition=keep, primary_key=["snapshot_date", "time_range", "rank"]),
        # The library and playlists as they are now: replaced on every run.
        dlt.resource(_lazy(lambda: spotify.saved_tracks(_client())), name="saved_tracks",
                     write_disposition="replace", primary_key="track_id"),
        dlt.resource(_lazy(lambda: spotify.playlists(_client(), _user_id())), name="playlists",
                     write_disposition="replace", primary_key="playlist_id"),
        dlt.resource(_lazy(lambda: spotify.playlist_items(_client(), _user_id())), name="playlist_items",
                     write_disposition="replace", primary_key=["playlist_id", "position"]),
        dlt.resource(_lazy(lambda: spotify.followed_artists(_client())), name="followed_artists",
                     write_disposition="replace", primary_key="artist_id"),
    ]


@dlt_assets(
    dlt_source=spotify_source(),
    dlt_pipeline=dlt.pipeline(
        pipeline_name="spotify",
        dataset_name="source",
        destination=storage.dlt_destination(PROJECT_DIR),
    ),
    group_name="spotify_ingest",
    name="spotify",
    dagster_dlt_translator=SpotifyDltTranslator(),
    pool=LAKE_POOL,
)
def spotify_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    if not spotify.connected():
        context.log.info(
            "No Spotify account connected: loading the sample listening history. To load your own, "
            "run `uv run python -m spotify_platform.connect` (README: 'Use your own Spotify data')."
        )
    yield from dlt.run(context=context)


# ---------------------------------------------------------------------------
# dbt: transforms the Spotify tables into dims and facts
# ---------------------------------------------------------------------------


@dbt_assets(
    manifest=spotify_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
    pool=LAKE_POOL,
)
def spotify_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------------------
# Schedule: Spotify keeps only the last 50 plays, so collect them often
# ---------------------------------------------------------------------------

spotify_sync = define_asset_job(
    "spotify_sync",
    selection=AssetSelection.groups("spotify_ingest").downstream(),
    description="Load the latest plays and rankings from Spotify and rebuild the models.",
)

# 50 plays last about three hours; every 30 minutes leaves room for a missed run
# or two. On from the start once an account is connected: the sample needs no
# schedule. Switch it on or off in the Crows Nest's Pipelines panel or in Dagster.
spotify_sync_schedule = ScheduleDefinition(
    name="spotify_sync_every_30_minutes",
    job=spotify_sync,
    cron_schedule="*/30 * * * *",
    default_status=DefaultScheduleStatus.RUNNING if spotify.connected() else DefaultScheduleStatus.STOPPED,
)
