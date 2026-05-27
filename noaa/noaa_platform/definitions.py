from dagster import Definitions, load_assets_from_modules
from dagster_dbt import DbtCliResource
from . import assets
from .assets import noaa_dbt_project

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={
        "dbt": DbtCliResource(project_dir=noaa_dbt_project),
    },
)
