from pathlib import Path
import duckdb
from dagster import AssetExecutionContext, AssetKey, asset
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets

PROJECT_DIR = Path(__file__).parent.parent  # noaa/
DB_PATH = PROJECT_DIR / "noaa.duckdb"
CSV_PATH = PROJECT_DIR / "seeds" / "guam_2025.csv"

noaa_dbt_project = DbtProject(project_dir=PROJECT_DIR)
noaa_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business)."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


@asset(
    key=AssetKey(["noaa", "guam_2025"]),
    group_name="noaa_ingest",
)
def noaa_guam_2025_raw(context: AssetExecutionContext) -> None:
    """Load Guam 2025 AIS CSV into noaa.duckdb raw.guam_2025.

    The CSV is a 3.2M-row static historical dataset downloaded from NOAA
    Marine Cadastre. This asset replaces the manual scripts/load_ais.py.
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"AIS data not found at {CSV_PATH}. "
            "Download from https://marinecadastre.gov/ais/ "
            "and save as noaa/seeds/guam_2025.csv."
        )

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        context.log.info(f"Loading {CSV_PATH.name} → raw.guam_2025 (may take a minute)...")
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.guam_2025 AS
            SELECT * FROM read_csv('{CSV_PATH}', header = true)
        """)
        count = con.execute("SELECT COUNT(*) FROM raw.guam_2025").fetchone()[0]
        context.log.info(f"Loaded {count:,} rows into raw.guam_2025.")
    finally:
        con.close()


@dbt_assets(
    manifest=noaa_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
)
def noaa_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
