from pathlib import Path
from dagster import AssetExecutionContext
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets

PROJECT_ROOT = Path(__file__).parent.parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt" / "optimist"

optimist_dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
optimist_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business)."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        fqn = dbt_resource_props.get("fqn", [])
        # fqn: ["optimist", "source", "stg_orders"] → group "source"
        # fqn: ["optimist", "business", "dim_date"]  → group "business"
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


@dbt_assets(
    manifest=optimist_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
)
def optimist_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------------------
# Ingestion layer — dlt pipelines
# ---------------------------------------------------------------------------
# Use @dlt_assets to load data from any external source into DuckDB before
# dbt runs. Each pipeline maps to one source system (REST API, database,
# file store, etc.) and lands its tables in the "source" schema so dbt can
# pick them up as normal sources.
#
# Pattern (copy and adapt for each source):
#
#   import dlt
#   from dagster_dlt import DagsterDltResource, dlt_assets
#
#   @dlt_assets(
#       dlt_source=my_source(),          # any dlt source or verified source
#       dlt_pipeline=dlt.pipeline(
#           pipeline_name="my_pipeline",
#           dataset_name="source",       # → lakehouse.source schema
#           destination="duckdb",
#           credentials="data/lakehouse.duckdb",
#       ),
#       group_name="source",
#   )
#   def my_source_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
#       yield from dlt.run(context=context)
#
# Add DagsterDltResource to definitions.py resources when wiring this up:
#   from dagster_dlt import DagsterDltResource
#   resources = { ..., "dlt": DagsterDltResource() }
#
# Full guide: docs/ingestion.md
