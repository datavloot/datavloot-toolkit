from pathlib import Path
from dagster import AssetExecutionContext
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "<project_name>.duckdb"

project_dbt_project = DbtProject(project_dir=PROJECT_DIR)
project_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business)."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


@dbt_assets(
    manifest=project_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
)
def project_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------------------
# Ingestion — add dlt pipelines here
# ---------------------------------------------------------------------------
# See the NOAA demo for a complete worked example: optimist demo
#
# Pattern:
#
#   import dlt
#   from dagster_dlt import DagsterDltResource, dlt_assets
#
#   @dlt_assets(
#       dlt_source=my_source(),
#       dlt_pipeline=dlt.pipeline(
#           pipeline_name="my_pipeline",
#           dataset_name="source",
#           destination="duckdb",
#           credentials=str(DB_PATH),
#       ),
#       group_name="source",
#   )
#   def my_source_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
#       yield from dlt.run(context=context)
#
# Add DagsterDltResource to definitions.py resources when wiring this up.
