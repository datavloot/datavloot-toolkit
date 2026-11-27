from dotenv import load_dotenv
load_dotenv()

from dagster import Definitions, in_process_executor, load_assets_from_modules
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource
from . import assets
from .assets import github_dbt_project, github_refresh, github_refresh_schedule
from .lake_maintenance import lake_maintenance, lake_maintenance_schedule

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[lake_maintenance, github_refresh],
    schedules=[lake_maintenance_schedule, github_refresh_schedule],
    # All steps of a run in the run's own process: the code is loaded once per
    # run instead of once per step, which on Windows takes tens of seconds each
    # time. Running steps side by side would gain nothing, because the lake pool
    # (dagster.yaml) lets one writer at a time in anyway.
    executor=in_process_executor,
    resources={
        "dbt": DbtCliResource(project_dir=github_dbt_project),
        "dlt": DagsterDltResource(),
    },
)
