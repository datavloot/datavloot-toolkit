from dotenv import load_dotenv
load_dotenv()

from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    in_process_executor,
    load_assets_from_modules,
)
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource
from . import assets
from .assets import energyzero_assets, open_meteo_assets, green_energy_dbt_assets, green_energy_dbt_project
from .lake_maintenance import lake_maintenance, lake_maintenance_schedule

all_assets = load_assets_from_modules([assets])

# Every morning: load yesterday's prices and weather, then `dbt build` (models and
# tests). Both sources load closed days only (up to yesterday, UTC), so at 07:00
# Dutch time yesterday is complete for both. The dlt cursors make each run fetch
# only what is new. Runs only while Dagster runs (datavloot start / autostart).
daily_refresh = define_asset_job(
    name="daily_refresh",
    selection=AssetSelection.assets(energyzero_assets, open_meteo_assets, green_energy_dbt_assets),
)

daily_refresh_schedule = ScheduleDefinition(
    job=daily_refresh,
    cron_schedule="0 7 * * *",
    execution_timezone="Europe/Amsterdam",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=all_assets,
    jobs=[daily_refresh, lake_maintenance],
    schedules=[daily_refresh_schedule, lake_maintenance_schedule],
    # All steps of a run in the run's own process: the code is loaded once per
    # run instead of once per step, which on Windows takes tens of seconds each
    # time. Running steps side by side would gain nothing, because the lake pool
    # (dagster.yaml) lets one writer at a time in anyway.
    executor=in_process_executor,
    resources={
        "dbt": DbtCliResource(project_dir=green_energy_dbt_project),
        "dlt": DagsterDltResource(),
    },
)
