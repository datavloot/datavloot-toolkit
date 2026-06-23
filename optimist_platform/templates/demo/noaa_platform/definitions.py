from dagster import Definitions, in_process_executor, load_assets_from_modules
from dagster_dbt import DbtCliResource
from dagster_dlt import DagsterDltResource
from . import assets
from .assets import noaa_dbt_project

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    executor=in_process_executor,
    resources={
        "dbt": DbtCliResource(project_dir=noaa_dbt_project),
        "dlt": DagsterDltResource(),
    },
)
