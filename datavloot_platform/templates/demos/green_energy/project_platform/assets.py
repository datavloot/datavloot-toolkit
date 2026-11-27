import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import dlt
from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import DbtProject, DbtCliResource, DagsterDbtTranslator, dbt_assets
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dlt.sources.helpers import requests  # requests with retries built in

from datavloot_platform import storage

PROJECT_DIR = Path(__file__).parent.parent

# Every asset that writes to the lake runs in this pool. dagster.yaml limits each
# pool to one at a time, because the lake takes one commit at a time.
LAKE_POOL = "lake"

# Dagster is the only production writer: it builds the prod target, while a
# plain `dbt run` builds dev (see profiles.yml). The dbt resource inherits it.
# install_deps=False: under `datavloot start`, prepare_if_dev would otherwise run
# `dbt deps` on every code load, which first deletes dbt_packages/. When the code
# server and a run load at once, that fails on Windows (WinError 32) and every
# run fails with it. `datavloot new --from`, `update` and the installers run
# `dbt deps` themselves; after changing packages.yml, run `uv run dbt deps`.
green_energy_dbt_project = DbtProject(project_dir=PROJECT_DIR, target="prod", install_deps=False)
green_energy_dbt_project.prepare_if_dev()


class LayerGroupTranslator(DagsterDbtTranslator):
    """Groups dbt assets by their folder layer (source / business); a package's assets by package."""

    def get_group_name(self, dbt_resource_props: dict) -> str:
        # By folder, Elementary's models would land in one group per subfolder.
        package = dbt_resource_props.get("package_name")
        if package and package != green_energy_dbt_project.name:
            return package
        fqn = dbt_resource_props.get("fqn", [])
        if len(fqn) >= 2:
            return fqn[-2]
        return "default"


class SourceTableTranslator(DagsterDltTranslator):
    """Gives a dlt table the asset key dbt gives the same table as a source.

    dbt calls the source table `energyzero.day_ahead_prices` (source name, table
    name in _sources.yml); dlt's own key would be `dlt_energyzero_day_ahead_prices`.
    With the same key on both sides, Dagster draws the edge from the load to the
    staging model, and runs them in that order.
    """

    def get_asset_spec(self, data):
        spec = super().get_asset_spec(data)
        return spec.replace_attributes(
            key=AssetKey([data.resource.source_name, data.resource.name]),
            deps=[],  # no separate "external" asset for the API itself
        )


# ---------------------------------------------------------------------------
# Ingestion: closed days only, from 2025-01-01 up to and including yesterday (UTC)
# ---------------------------------------------------------------------------

START = "2025-01-01T00:00:00Z"
LOCATIONS_CSV = PROJECT_DIR / "seeds" / "locations.csv"  # also dbt's seed for dim_location


def _yesterday() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


# EnergyZero: day-ahead electricity prices, one per hour, in UTC

@dlt.resource(name="day_ahead_prices", write_disposition="merge", primary_key="reading_date")
def day_ahead_prices(
    cursor=dlt.sources.incremental("reading_date", initial_value=START),
):
    """Hourly day-ahead prices. The first run backfills from 2025-01-01; later runs
    start at the last hour already loaded (that day is fetched again, and merged)."""
    start = cursor.last_value[:10]
    end = str(_yesterday())
    if start > end:
        return  # nothing new yet
    response = requests.get(
        "https://api.energyzero.nl/v1/energyprices",
        params={
            "fromDate": f"{start}T00:00:00.000Z",
            "tillDate": f"{end}T23:59:59.999Z",
            "interval": 4,  # one price per hour
            "usageType": 1,  # electricity
            "inclBtw": "false",  # excl. VAT
        },
    )
    response.raise_for_status()
    for row in response.json()["Prices"]:
        yield {"reading_date": row["readingDate"], "price_eur_kwh": row["price"]}


@dlt.source(name="energyzero")
def energyzero_source():
    return day_ahead_prices()


# Open-Meteo: hourly weather per location, from the ERA5 archive, in UTC

WEATHER_VARIABLES = {
    # Open-Meteo name: our column name, with the unit in it
    "wind_speed_10m": "wind_speed_10m_ms",
    "shortwave_radiation": "shortwave_radiation_wm2",
    "temperature_2m": "temperature_2m_c",
}


@dlt.resource(
    name="hourly_weather",
    write_disposition="merge",
    primary_key=["location_code", "observed_at"],
)
def hourly_weather(
    cursor=dlt.sources.incremental("observed_at", initial_value=START),
):
    """Hourly weather for every location in seeds/locations.csv: one call per location."""
    start = cursor.last_value[:10]
    end = str(_yesterday())
    if start > end:
        return
    with open(LOCATIONS_CSV, newline="", encoding="utf-8") as f:
        locations = list(csv.DictReader(f))
    for loc in locations:
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "start_date": start,
                "end_date": end,
                "hourly": ",".join(WEATHER_VARIABLES),
                "wind_speed_unit": "ms",
                "timezone": "UTC",
            },
        )
        response.raise_for_status()
        hourly = response.json()["hourly"]
        for i, time in enumerate(hourly["time"]):
            row = {"location_code": loc["location_code"], "observed_at": f"{time}:00Z"}
            for api_name, column in WEATHER_VARIABLES.items():
                row[column] = hourly[api_name][i]
            yield row


@dlt.source(name="open_meteo")
def open_meteo_source():
    return hourly_weather()


def _dlt_pipeline(name: str):
    return dlt.pipeline(
        pipeline_name=f"green_energy_{name}",
        dataset_name="source",  # the `source` schema in the lake
        destination=storage.dlt_destination(PROJECT_DIR),
    )


@dlt_assets(
    dlt_source=energyzero_source(),
    dlt_pipeline=_dlt_pipeline("energyzero"),
    name="energyzero",
    group_name="ingest",
    dagster_dlt_translator=SourceTableTranslator(),
    pool=LAKE_POOL,  # it writes to the lake: one writer at a time
)
def energyzero_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


@dlt_assets(
    dlt_source=open_meteo_source(),
    dlt_pipeline=_dlt_pipeline("open_meteo"),
    name="open_meteo",
    group_name="ingest",
    dagster_dlt_translator=SourceTableTranslator(),
    pool=LAKE_POOL,
)
def open_meteo_assets(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


# ---------------------------------------------------------------------------
# dbt: staging, dimensions, facts and their tests
# ---------------------------------------------------------------------------

@dbt_assets(
    manifest=green_energy_dbt_project.manifest_path,
    dagster_dbt_translator=LayerGroupTranslator(),
    pool=LAKE_POOL,
)
def green_energy_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
