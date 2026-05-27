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
