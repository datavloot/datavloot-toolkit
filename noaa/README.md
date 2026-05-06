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
scripts/
└── load_ais.py         # one-time script to load AIS data into DuckDB
seeds/
├── ports.csv           # global port reference data (3,804 rows)
└── _seeds.yml          # seed descriptions and tests
models/
├── source/
│   ├── _sources.yml    # AIS source definition (raw.guam_2025)
│   ├── _schema.yml     # staging model docs and tests
│   └── stg_noaa__guam_2025.sql
└── business/
    ├── dimensions/
    │   ├── _dim_configs.yml   # dim_vessel, dim_port
    │   ├── dim_vessel.sql
    │   └── dim_port.sql
    └── facts/
        ├── _fct_configs.yml   # fct_port_event
        └── fct_port_event.sql
tests/
├── assert_fct_port_event_not_in_future.sql
└── assert_stg_noaa_sog_in_range.sql
```

---

## Getting started

### 1. Install dbt-duckdb

```bash
pip install dbt-duckdb
```

### 2. Load the AIS source data into DuckDB

The AIS dataset (3.2M rows) is too large for a dbt seed — it is loaded once into a
persistent DuckDB file and then referenced as a source.

```bash
cd /path/to/noaa
python3 scripts/load_ais.py
```

This creates `noaa.duckdb` and loads `seeds/guam_2025.csv` into `raw.guam_2025`.

### 3. Install the optimist-toolkit package

```bash
dbt deps
```

### 4. Load seed data (ports reference table)

```bash
dbt seed
```

### 5. Build all models

```bash
dbt run
```

### 6. Run tests

```bash
dbt test
```

---

## Data lineage

```
seeds/ports.csv          →  dim_port
raw.guam_2025 (DuckDB)   →  stg_noaa__guam_2025  →  dim_vessel
                                                  →  fct_port_event  →  dim_vessel (FK)
                                                                     →  dim_port   (FK)
                                                                     →  dim_date   (FK)
```
