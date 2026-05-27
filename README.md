# optimist-toolkit

An open-source data platform for small businesses — a complete, self-hosted alternative to big cloud SaaS data platforms.

Built on battle-tested open-source tools with no monthly fees, no vendor lock-in, and no cloud required if not desired.

| Component | Tool | Role |
|---|---|---|
| Orchestration | [Dagster](https://dagster.io) | Schedule and monitor your data pipelines |
| Ingestion | [dlt](https://dlthub.com) | Load data from APIs, databases, and files into DuckDB |
| Transformation | [dbt](https://getdbt.com) | Transform, test, and document your data |
| Storage | [DuckDB](https://duckdb.org) + [DuckLake](https://ducklake.select) | Local lakehouse with two-layer architecture |
| Data quality | [Elementary](https://elementary-data.com) | Monitors, alerts, and reports on data quality |

---

## Getting started

### Prerequisites

- Python 3.10–3.14
- Git

### 1. Create your project from this template

Click **Use this template** on GitHub to create your own repository, then clone it:

```bash
git clone https://github.com/your-org/your-data-platform
cd your-data-platform
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Initialize the lakehouse catalog

Creates the DuckLake catalog file and sets up source and business schemas:

```bash
python setup_catalog.py
```

### 4. Install dbt packages

```bash
cd dbt/optimist
dbt deps
cd ../..
```

### 5. Start the platform

```bash
dagster dev
```

Open [http://localhost:3000](http://localhost:3000) to see the Dagster UI.

---

## Data layers

This platform uses a two-layer architecture, intentionally kept simple for small teams:

```
source    →    business
 raw &          modelled
 staged         tables
 views
```

Rather than the traditional three-layer medallion (bronze → silver → gold), the **source** layer combines raw data landing and staging into a single step — your source models read directly from ingested data and expose clean, audited views. The **business** layer builds the dimensions, facts, and aggregations your team actually queries.

This keeps things simple: fewer layers, less pipeline complexity, faster setup.

---

## Building your platform with AI

This toolkit is designed to be used in conversation with an AI assistant — no data engineering background required.

Think of it as a **captain and crew** relationship: you are the captain who knows your business and your data sources. The AI is the crew that handles the technical implementation. You describe what you need, the AI builds it using the toolkit conventions, and you review and approve.

A dedicated agent guide lives at [CLAUDE.md](CLAUDE.md) and in every scaffold project at `scaffold/CLAUDE.md`. Hand it to your AI assistant at the start of a session and it will know exactly how to work with this toolkit.

The [`noaa/`](noaa/) example project was built entirely this way — a captain with no data engineering skills directed an AI crew through the full workflow, from raw AIS vessel broadcasts to a complete dimensional model. The conversation that produced it is included at [noaa/conversation.md](noaa/conversation.md).

---

## Starting a new project

Copy the `scaffold/` directory as the foundation for any new project using this toolkit:

```
scaffold/
├── CLAUDE.md                          # AI agent workflow guide (captain/crew model)
├── packages.yml                       # points to this toolkit
├── dbt_project.yml                    # project config with sensible defaults
├── profiles.yml                       # DuckDB + DuckLake connection config
├── seeds/
│   ├── _seeds.yml                     # seed documentation template
│   ├── how_to.md                      # when to use seeds
│   └── priority_levels.csv            # example seed
└── models/
    ├── source/
    │   ├── _sources.yml               # source definition template
    │   └── _schema.yml                # staging model documentation template
    └── business/
        ├── dimensions/_dim_configs.yml
        └── facts/_fct_configs.yml
```

Fill in `<project_name>` in `dbt_project.yml`, run `dbt deps`, then follow `scaffold/CLAUDE.md`.

---

## Example project

The [`noaa/`](noaa/) directory is a complete consuming project built on this toolkit. It uses
publicly available AIS vessel position broadcasts from [NOAA](https://www.noaa.gov/) near Guam
(2025) combined with global port reference data. It demonstrates the full workflow:

- Loading a large raw dataset (3.2 M rows) into DuckDB as a source
- Staging with audit columns and deduplication
- Deriving arrival and departure events from raw position broadcasts using window functions
- Building `dim_vessel`, `dim_port`, and `fct_port_event` with toolkit macros
- Configuring data quality tests at every layer

See [noaa/README.md](noaa/README.md).

---

## Adding your own data

### 1. Ingest raw data

Write a Dagster asset in `optimist_platform/assets.py` that loads your source data into `lakehouse.source`. See [assets.py](optimist_platform/assets.py) for the DuckDB connection pattern.

### 2. Define your sources in dbt

Copy the templates from `dbt/optimist/models/source/` and fill in your source tables.

### 3. Stage with one line

```sql
-- dbt/optimist/models/source/stg_harbor__vessels.sql
{{ optimist.stage_source('harbor', 'vessels') }}
```

### 4. Build business models

```sql
-- dbt/optimist/models/business/dimensions/dim_vessel.sql
{{ optimist.build_dimension(
    source_model = 'stg_harbor__vessels',
    natural_key  = 'vessel_id',
    attributes   = ['vessel_name', 'flag', 'vessel_type']
) }}
```

```sql
-- dbt/optimist/models/business/facts/fct_port_call.sql
{{ optimist.build_fact(
    source_model   = 'stg_harbor__port_calls',
    natural_key    = 'port_call_id',
    dimensions     = [{'model': 'dim_vessel', 'key': 'vessel_id'}],
    measures       = ['duration_hours', 'cargo_tonnes']
) }}
```

---

## Scaling up

This platform runs entirely on a local machine out of the box, but each component scales independently when your needs grow:

| Step | What changes | What stays the same |
|---|---|---|
| **Cloud VM** | Move the whole platform to EC2 / GCE / Azure VM | Nothing — runs identically |
| **Cloud storage** | Point DuckLake at S3, GCS, or Azure Blob instead of a local file | All dbt models and Dagster assets |
| **Managed orchestration** | Switch to [Dagster Cloud](https://dagster.io/cloud) | Your `definitions.py` and `assets.py` |
| **Cloud warehouse** | Swap `dbt-duckdb` for `dbt-snowflake`, `dbt-bigquery`, etc. | All models and macros (mostly portable SQL) |

You can take any of these steps independently and in any order. Start local, move to cloud when it makes sense.

---

## Using the dbt package in an existing project

If you already have a dbt project and only want the standardized macros, install the package via `dbt deps`:

```yaml
# packages.yml
packages:
  - git: "https://gitlab.com/mycelium4483613/optimist-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: main        # pin to a tag or commit SHA for reproducible builds
```

Then install:

```bash
dbt deps
```

---

## Documentation

- [Getting started with the dbt package](docs/getting-started.md)
- [Ingestion layer — loading data with dlt](docs/ingestion.md)
- [Source layer — auto-staging and audit columns](docs/source-layer.md)
- [Business layer — dimensions, facts, and surrogate keys](docs/business-layer.md)

---

## Features

| Feature | Description |
|---|---|
| `stage_source` | Auto-generate a staging model; introspects source schema, appends audit columns, supports deduplication and incremental loading |
| `add_audit_columns` | Emit `_loaded_at`, `_source_name`, `_source_table` in any SELECT |
| `build_dimension` | Config-driven dimension with surrogate key, optional dedup, and three source options |
| `build_fact` | Config-driven fact with automatic dimension LEFT JOINs and surrogate key |
| `generate_surrogate_key` | MD5 surrogate key over a list of columns, available standalone |
| `dim_date` | Shared calendar date dimension (configurable range, default 2020–2030) |
| `dim_time` | Shared time-of-day dimension at minute granularity (1 440 rows) |

---

## Stack versions

| Package | Version constraint |
|---|---|
| Python | >=3.10, <3.15 |
| dagster | latest |
| dagster-dbt | latest |
| dbt-core | latest |
| dbt-duckdb | latest |
| ducklake | latest |
| elementary-data | >=0.16.0 |
