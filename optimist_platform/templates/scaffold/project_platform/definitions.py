from dotenv import load_dotenv
load_dotenv()

from dagster import Definitions, load_assets_from_modules
from dagster_dbt import DbtCliResource
from . import assets
from .assets import project_dbt_project

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    resources={
        "dbt": DbtCliResource(project_dir=project_dbt_project),
    },
)
