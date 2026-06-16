# noaa

A dbt project built on [optimist-toolkit](https://gitlab.com/mycelium4483613/optimist-toolkit).

This project is an **example** of how a project is set up with the optimist toolkit. It uses
publicly available data from the [National Oceanic and Atmospheric Administration (NOAA)](https://www.noaa.gov/)
to demonstrate how to go from raw source data to a clean, tested, analytics-ready dbt project.

The data covers AIS vessel position broadcasts near Guam for 2025, combined with global port
reference data. The output answers questions like:
- How many vessels arrived at Apra Harbor in a given month?
- What is the busiest departure hour of the day?
- Which vessel types arrive most frequently?

---

## What this project demonstrates

- Scaffolding a new consuming project from the optimist-toolkit template
- Loading a large raw dataset (3.2M rows) into DuckDB as a source — not a seed
- Loading small reference data (ports) as a dbt seed
- Staging source tables with audit columns and deduplication
- Deriving arrival/departure events from raw position broadcasts using window functions
- Building dimension and fact models using toolkit macros
- Configuring data quality tests at every layer

---

## Project structure

```
data/
└── guam_2025.csv             # AIS position broadcasts — download separately (see Getting started)
noaa_platform/                # Dagster platform layer (assets, definitions)
seeds/
├── ports.csv                 # global port reference data (3,804 rows)
├── sea_state_categories.csv  # Beaufort wind scale thresholds
└── _seeds.yml                # seed descriptions and tests
models/
├── source/
│   ├── ais/
│   │   ├── _sources.yml      # AIS source definition (raw.guam_2025)
│   │   ├── _schema.yml       # staging model docs and tests
│   │   └── stg_noaa__guam_2025.sql
│   └── open_meteo/
│       ├── _sources.yml      # Open-Meteo source definition
│       ├── _schema.yml
│       └── stg_open_meteo__guam_atmo_hourly.sql
└── business/
    ├── dimensions/
    │   ├── _dim_configs.yml  # dim_vessel, dim_port, dim_sea_state
    │   ├── dim_vessel.sql
    │   ├── dim_port.sql
    │   └── dim_sea_state.sql
    └── facts/
        ├── _fct_configs.yml  # fct_port_event
        └── fct_port_event.sql
tests/
├── assert_fct_port_event_not_in_future.sql
└── assert_stg_noaa_sog_in_range.sql
pyproject.toml                # Python package config; points Dagster at noaa_platform.definitions
```

---

## Getting started

All commands run from inside the `noaa/` directory. You'll need **Python 3.10–3.14** and **git**.

### 1. Install dependencies and activate the environment

**With uv** (recommended — [install uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it):

```bash
uv sync
source .venv/bin/activate   # macOS / Linux
.venv\Scripts\activate      # Windows
```

**With pip** (no extra tools needed):

```bash
pip install .
```

> If using pip without an active virtual environment, create one first:
> `python -m venv .venv` then activate it as shown above.

All subsequent commands (`dbt`, `dagster`, `duckdb`) run in the activated environment — no prefix needed.

### 2. Install the optimist-toolkit dbt package

```bash
dbt deps
```

### 3. Get the AIS data

Download the Guam 2025 AIS zone file from [marinecadastre.gov/ais](https://marinecadastre.gov/ais/)
and save it as `data/guam_2025.csv`.

### 4. Generate the dbt manifest

Dagster needs a compiled manifest before it can start:

```bash
dbt parse
```

### 5. Start Dagster

```bash
dagster dev
```

Open [http://localhost:3000](http://localhost:3000).

In the **Asset Catalog**, materialise assets in this order:

| Step | Asset | What it does |
|---|---|---|
| 1 | `noaa/guam_2025` | Loads `data/guam_2025.csv` → `noaa.duckdb` `raw.guam_2025` |
| 2 | `open_meteo/guam_atmo_hourly` | Fetches hourly wind data from Open-Meteo archive API → `noaa.duckdb` |
| 3 | All remaining assets | Runs `dbt build` — seeds ports, stages sources, builds dims and fact, runs tests |

To re-run only the dbt models without re-loading raw data, select the dbt assets and click **Materialize selected**.

Dagster persists run history, asset metadata, and test results in `noaa_platform/` — check the **Runs** tab for logs if a build fails.

---

## Querying the results

The warehouse is a single DuckDB file at `noaa/noaa.duckdb`. All business-layer tables land in the `noaa_business` schema.

### Install the DuckDB CLI

```bash
# Download the standalone CLI binary (Linux x86-64)
curl -Lo /tmp/duckdb.zip https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip /tmp/duckdb.zip -d ~/.local/bin/
chmod +x ~/.local/bin/duckdb
```

### Open the database

```bash
duckdb noaa.duckdb
```

### Useful queries

```sql
-- List all tables
SHOW ALL TABLES;

-- Total port events
SELECT COUNT(*) FROM noaa_business.fct_port_event;

-- Arrivals per month (is_departure = false means arrival)
SELECT
    DATE_TRUNC('month', event_time) AS month,
    COUNT(*) AS arrivals
FROM noaa_business.fct_port_event
WHERE NOT is_departure
GROUP BY 1
ORDER BY 1;

-- Busiest hour of day for departures
SELECT
    HOUR(event_time) AS hour_of_day,
    COUNT(*) AS departures
FROM noaa_business.fct_port_event
WHERE is_departure
GROUP BY 1
ORDER BY 2 DESC;

-- Vessel types with most port events
SELECT
    v.vessel_type,
    COUNT(*) AS port_events
FROM noaa_business.fct_port_event f
LEFT JOIN noaa_business.dim_vessel v ON f.dim_vessel_key = v.dim_vessel_key
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
```

Type `.quit` to exit the DuckDB shell.

---

## Data lineage

```
seeds/ports.csv                    →  dim_port
seeds/sea_state_categories.csv     →  dim_sea_state
raw.guam_2025 (DuckDB)             →  stg_noaa__guam_2025         →  dim_vessel
Open-Meteo archive API (dlt)       →  stg_open_meteo__guam_atmo_hourly  ↘
                                                                      fct_port_event  →  dim_vessel    (FK)
                                                                                      →  dim_port      (FK)
                                                                                      →  dim_date      (FK)
                                                                                      →  dim_time      (FK)
                                                                                      →  dim_sea_state (FK)
```
