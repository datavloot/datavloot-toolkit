from pathlib import Path
from datetime import date
import duckdb
import dlt
from dlt.sources.helpers import requests as dlt_requests
from dlt.destinations import duckdb as duckdb_destination
from dagster import AssetExecutionContext, AssetKey, asset
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets
from dagster_dlt import DagsterDltResource, dlt_assets

PROJECT_DIR = Path(__file__).parent.parent  # noaa/
DB_PATH = PROJECT_DIR / "noaa.duckdb"
CSV_PATH = PROJECT_DIR / "data" / "guam_2025.csv"

noaa_dbt_project = DbtProject(project_dir=PROJECT_DIR)
noaa_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business)."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


# ---------------------------------------------------------------------------
# AIS ingestion — static historical CSV
# ---------------------------------------------------------------------------

@asset(
    key=AssetKey(["noaa", "guam_2025"]),
    group_name="noaa_ingest",
)
def noaa_guam_2025_raw(context: AssetExecutionContext) -> None:
    """Load Guam 2025 AIS CSV into noaa.duckdb raw.guam_2025."""
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


# ---------------------------------------------------------------------------
# Marine weather ingestion — Open-Meteo (free, no API key)
# ---------------------------------------------------------------------------

GUAM_LAT = 13.4406
GUAM_LON = 144.7937


@dlt.resource(
    name="guam_marine_hourly",
    write_disposition="merge",
    primary_key="timestamp",
)
def guam_marine_hourly(
    updated_at: dlt.sources.incremental[str] = dlt.sources.incremental(
        "timestamp",
        initial_value="2025-01-01T00:00",
    ),
):
    """Hourly marine and wind conditions near Guam from Open-Meteo.

    On first run: backfills from 2025-01-01.
    On subsequent runs: fetches only new hours from the last loaded timestamp.
    """
    start_date = (updated_at.last_value or "2025-01-01T00:00")[:10]
    end_date = str(date.today())
    if start_date >= end_date:
        return

    response = dlt_requests.get(
        "https://marine-api.open-meteo.com/v1/marine",
        params={
            "latitude": GUAM_LAT,
            "longitude": GUAM_LON,
            "hourly": ",".join([
                "wave_height",
                "wave_direction",
                "wave_period",
                "wind_wave_height",
                "swell_wave_height",
                "swell_wave_direction",
                "swell_wave_period",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
            ]),
            "wind_speed_unit": "kn",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "UTC",
        },
    )
    response.raise_for_status()
    hourly = response.json()["hourly"]
    times = hourly["time"]
    n = len(times)

    for i, ts in enumerate(times):
        yield {
            "timestamp":               ts,
            "wave_height_m":           hourly.get("wave_height",          [None] * n)[i],
            "wave_direction_deg":      hourly.get("wave_direction",        [None] * n)[i],
            "wave_period_s":           hourly.get("wave_period",           [None] * n)[i],
            "wind_wave_height_m":      hourly.get("wind_wave_height",      [None] * n)[i],
            "swell_wave_height_m":     hourly.get("swell_wave_height",     [None] * n)[i],
            "swell_wave_direction_deg": hourly.get("swell_wave_direction", [None] * n)[i],
            "swell_wave_period_s":     hourly.get("swell_wave_period",     [None] * n)[i],
            "wind_speed_10m_kn":       hourly.get("wind_speed_10m",        [None] * n)[i],
            "wind_direction_10m_deg":  hourly.get("wind_direction_10m",    [None] * n)[i],
            "wind_gusts_10m_kn":       hourly.get("wind_gusts_10m",        [None] * n)[i],
        }


@dlt.source(name="open_meteo")
def open_meteo_marine_source():
    return guam_marine_hourly()


@dlt_assets(
    dlt_source=open_meteo_marine_source(),
    dlt_pipeline=dlt.pipeline(
        pipeline_name="open_meteo_marine",
        dataset_name="source",
        destination=duckdb_destination(credentials=str(DB_PATH)),
    ),
    group_name="noaa_ingest",
    name="open_meteo",
)
def open_meteo_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


# ---------------------------------------------------------------------------
# dbt — transforms all ingested sources into dims and facts
# ---------------------------------------------------------------------------

@dbt_assets(
    manifest=noaa_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
)
def noaa_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
