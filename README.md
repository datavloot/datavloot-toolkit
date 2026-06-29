# optimist-toolkit

A self-hosted data platform for data engineers who want to own their stack rather than be trained on someone else's.

Most data engineering roles today make you proficient in a vendor — Databricks, Snowflake, a managed orchestrator. That knowledge doesn't transfer when the vendor changes or the contract ends. The Optimist gives you a complete, working platform built on open-source tools that you run and understand yourself, so the expertise stays with you.

The stack:

| Component | Tool | Role |
|---|---|---|
| Orchestration | [Dagster](https://dagster.io) | Schedule and monitor your data pipelines |
| Ingestion | [dlt](https://dlthub.com) | Load data from APIs, databases, and files into DuckDB |
| Transformation | [dbt](https://getdbt.com) | Transform, test, and document your data |
| Storage | [DuckDB](https://duckdb.org) + [DuckLake](https://ducklake.select) | Local lakehouse with two-layer architecture |
| Data quality | [Elementary](https://elementary-data.com) | Monitors, alerts, and reports on data quality |
| Exploration | [Marimo](https://marimo.io) | Reactive notebooks for querying and visualising results |
| Dashboard | Crows Nest (built-in) | Unified browser interface for all of the above |

---

## Why this stack

All six tools are Python-native, open source, and run locally without cloud infrastructure. They were chosen because they compose cleanly: dlt loads into DuckDB, dbt transforms it, Dagster orchestrates both, Elementary monitors the output, and Marimo queries the result. Each tool does one job and exposes it through standard interfaces.

The alternatives — Databricks, Fivetran, Airflow on managed infrastructure, a cloud warehouse — are not wrong, but they carry a cost beyond the invoice: you become dependent on the platform, and the platform abstracts away the mechanics you should understand. This stack does not abstract. It uses proven open-source tooling of which the code can be downloaded and reviewed at any time to understand what is under te hood.

The Optimist is a fully functional data platform that runs on your local machine — not a toy or a tutorial environment, but the real thing. The intent is that once you've built and understood it locally, you can scale the same platform up to support an actual business, open source, fully owned, with no black boxes.

---

## Getting started

### Prerequisites

- Python 3.10–3.13 (3.12 recommended; 3.14 is not yet supported by all dependencies)
- Git
- A C compiler (required to build some dependencies from source)

  | OS | What you need | How to get it |
  |---|---|---|
  | **Windows** | Microsoft C++ Build Tools | Download from [visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/), select **Desktop development with C++** |
  | **macOS** | Xcode Command Line Tools | Run `xcode-select --install` in a terminal |
  | **Linux** | GCC | Run `sudo apt install build-essential` (Debian/Ubuntu) or `sudo yum install gcc` (RHEL/Fedora) |

### 1. Create your own repository

Create a new repository on GitHub or GitLab (empty is fine), then clone it and navigate into it.

### 2. Install the toolkit

```bash
pip install datavloot[optimist]
```

The `[optimist]` part installs the full Optimist stack (Dagster, dbt, dlt, DuckDB, Marimo, Elementary). Without it you get only the bare `datavloot` package with no tools.

If `pip` is not recognised (common on Windows), use:

```bash
python -m pip install datavloot[optimist]
```

If you see a `Failed to build cffi` error, ensure a C Compiler is installed (see Prerequisites above), then retry.

> **Note:** The first install downloads and builds a large number of packages (Dagster, dbt, dlt, Elementary, and their dependencies). Expect it to take 5–10 minutes. The prompt will return when it is done — let it run.


### 3. Scaffold a new project

```bash
datavloot new <my-project>
cd <my-project>
```

Please substitute 'my-project' here with the desired name of your project. The project name is inferred from the directory — all placeholders in config and code are substituted automatically.

Or try the NOAA worked example first:

```bash
datavloot demo
cd optimist-demo
pip install -e .   # install the demo's Python package
```

### 4. Install dependencies and dbt packages

```bash
pip install -e .   # install your project's Python package
dbt deps           # install the optimist dbt package — re-run whenever you upgrade or change packages.yml
dbt parse          # compile the manifest (required before first run)
```

### 5. Start the platform

```bash
datavloot start
```

This starts Dagster and the Crows Nest together and opens the dashboard at [http://localhost:8080](http://localhost:8080). Dagster is available separately at [http://localhost:3000](http://localhost:3000). Press Ctrl+C to stop both.

If you prefer two terminals, you can start them independently:

```bash
dagster dev          # terminal 1 — Dagster at http://localhost:3000
datavloot launch     # terminal 2 — Crows Nest at http://localhost:8080
```

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

This toolkit is designed to be used alongside an AI assistant. Not as an abstraction that removes the need to understand what you're building, but as a way to move faster while you're learning it.

The **captain and crew** model describes the workflow: you direct the session — you know your data sources, your domain, and what the output should look like. The AI handles implementation within the toolkit's conventions. You review, question, and approve. The understanding has to be yours; the AI accelerates getting there.

A dedicated agent guide lives at [data-instructions.md](data-instructions.md) and inside every project created with `datavloot new`. Hand it to your AI assistant at the start of a session so it knows the toolkit's conventions and can work within them.

This is also where AI genuinely opens doors. If you have strong domain knowledge and data instincts but haven't spent years writing dbt macros or wiring up Dagster assets, an AI assistant can bridge that gap — not by hiding the stack from you, but by letting you engage with it at the right level before all the implementation details are second nature. The [NOAA demo](datavloot_platform/templates/demo/) demonstrates this: someone with solid data understanding directed an AI through the full workflow, from raw AIS vessel broadcasts to a complete dimensional model. The conversation that produced it is at [conversation.md](datavloot_platform/templates/demo/conversation.md).

---

## Starting a new project

Run `datavloot new <path>` to scaffold a new project. The project name is inferred from the directory name you provide — all placeholders are substituted automatically. This copies the following structure:

```
<project-name>/
├── pyproject.toml                    # Python project config; wires Dagster to the platform module
├── .gitignore
├── data-instructions.md              # AI agent workflow guide (captain/crew model)
├── packages.yml                      # points to this toolkit's dbt package
├── dbt_project.yml                   # project config
├── profiles.yml                      # DuckDB connection config
├── notebooks/
│   └── explore.py                    # Marimo notebook for querying results
├── <project_name>_platform/          # Dagster layer (ready to run)
│   ├── __init__.py
│   ├── assets.py                     # dbt assets + commented dlt ingestion pattern
│   └── definitions.py
├── seeds/
│   ├── _seeds.yml
│   ├── how_to.md
│   └── priority_levels.csv
└── models/
    ├── source/
    │   ├── _sources.yml
    │   └── _schema.yml
    └── business/
        ├── dimensions/_dim_configs.yml
        └── facts/_fct_configs.yml
```

Run `dbt deps` after scaffolding, then follow `data-instructions.md`.

---

## Example project

The [NOAA demo](datavloot_platform/templates/demo/) is a complete consuming project built on this toolkit. It uses
publicly available AIS vessel position broadcasts from [NOAA](https://www.noaa.gov/) near Guam
(2025) combined with global port reference data. It demonstrates the full workflow:

- Loading a large raw dataset (3.2 M rows) into DuckDB as a source
- Staging with audit columns and deduplication
- Deriving arrival and departure events from raw position broadcasts using window functions
- Building `dim_vessel`, `dim_port`, and `fct_port_event` with toolkit macros
- Configuring data quality tests at every layer

Run `datavloot demo` to copy it locally, or browse it at [datavloot_platform/templates/demo/](datavloot_platform/templates/demo/). See the [demo README](datavloot_platform/templates/demo/README.md) for details.

---

## Adding your own data

### 1. Ingest raw data

For loading data from APIs, databases, or files, use [dlt](https://dlthub.com) — it handles pagination, schema inference, incremental loading, and writing directly into DuckDB with no boilerplate. Wrap the dlt pipeline in a Dagster asset so it appears in the UI and can be scheduled alongside your dbt models. See [`noaa_platform/assets.py`](datavloot_platform/templates/demo/noaa_platform/assets.py) in the demo for a working example of a dlt pipeline asset, and the [dlt docs](https://dlthub.com/docs) for available sources and connectors.

For simpler cases (reading a local file, calling a small API), a plain Dagster asset that writes directly to DuckDB is enough. See [assets.py](datavloot_platform/assets.py) for the DuckDB connection pattern.

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

## Running your pipeline

Once your assets and models are in place, materialise them in Dagster in dependency order:

| Step | What to materialise | What it does |
|---|---|---|
| 1 | Ingestion assets | Loads raw data into DuckDB via dlt or a plain Dagster asset |
| 2 | All dbt assets | Runs `dbt build` — seeds, staging, dimensions, facts, and tests |

Open the **Asset Catalog** at [http://localhost:3000](http://localhost:3000), select the assets, and click **Materialize selected**. Check the **Runs** tab for logs if anything fails.

To re-run only the dbt layer without re-loading raw data, select the dbt assets and materialise those alone.

---

## Exploring the data

Each project includes a `notebooks/` folder with Marimo notebooks that connect directly to your DuckDB database and let you query and visualise results in the browser — no SQL terminal needed.

```bash
marimo edit notebooks/explore.py
```

Open [http://localhost:2718](http://localhost:2718). To share a read-only view, use `marimo run notebooks/explore.py` instead.

The `datavloot new` scaffold includes a template notebook at `notebooks/explore.py` with placeholder cells to fill in for your own schema. See [`explore_noaa.py`](datavloot_platform/templates/demo/notebooks/explore_noaa.py) in the demo for a fully worked example.

You can also launch notebooks directly from the Crows Nest — the Notebooks panel lists all `.py` files in the `notebooks/` folder and lets you start them with a single click.

---

## The Crows Nest

The **Crows Nest** is a built-in unified dashboard that replaces the need to manage multiple browser tabs. Instead of switching between Dagster on :3000 and Marimo on :2718, you get one URL with everything.

`datavloot start` launches both Dagster and the Crows Nest together. To start the Crows Nest on its own (when Dagster is already running):

```bash
datavloot launch
```

Opens [http://localhost:8080](http://localhost:8080) with five panels:

| Panel | What it shows |
|---|---|
| **Pipelines** | Recent Dagster run history with status, job name, and duration. Auto-refreshes every 15 seconds. |
| **Data quality** | Elementary test results grouped by model with pass/fail/warn counts and a health bar. Click a model name to drill down into per-test results; click a test name to jump to a filtered view of all individual runs for that test. Includes an anomaly detection tab. |
| **SQL editor** | Read-only SQL editor connected directly to your DuckDB warehouse. Ctrl+Enter to run. Results paginate in the browser; no data leaves your machine. |
| **Catalog** | Every dbt model with its full column list (sourced from the actual warehouse schema, enriched with descriptions from dbt documentation where available), a last-run timestamp from dbt's model run history, and test results grouped by check. Falls back to `information_schema` for models not tracked by Elementary. |
| **Notebooks** | Lists all Marimo notebooks in your project's `notebooks/` folder. Click **Launch** to start a notebook and embed it directly in the panel. A **Close notebook** button in the panel header stops the Marimo process and returns you to the list. If Marimo stops for any other reason, the panel detects it within a few seconds and returns automatically. |

The **health banner** at the top of every panel shows live status indicators for Dagster, DuckDB, and Marimo — green when reachable, red when not. Panels that depend on a service that is temporarily unavailable (for example, DuckDB locked by an active Dagster run) return a descriptive message rather than an error.

The Crows Nest auto-discovers your project's DuckDB path from `profiles.yml` and infers the Elementary schema from your target schema name. No additional configuration is needed for standard projects. You can override any setting with environment variables:

| Variable | Default |
|---|---|
| `CROWSNEST_DUCKDB_PATH` | Read from `profiles.yml` |
| `CROWSNEST_DAGSTER_URL` | `http://localhost:3000/graphql` |
| `CROWSNEST_MARIMO_URL` | `http://127.0.0.1:2718` |
| `CROWSNEST_ELEMENTARY_SCHEMA` | Inferred from `profiles.yml` as `<target_schema>_elementary` (e.g. `noaa_elementary`) |

Options: `datavloot launch --port 8080 --host 127.0.0.1 --no-open`

---

## Scheduling and automation

By default, assets are materialised manually in the Dagster UI. To run pipelines automatically, Dagster provides three mechanisms:

| Approach | Use when |
|---|---|
| [Schedules](https://docs.dagster.io/guides/automate/schedules) | You want assets to run on a fixed cron interval (e.g. nightly at 02:00) |
| [Sensors](https://docs.dagster.io/guides/automate/sensors) | You want to react to an event — a new file, an API update, a threshold breach |
| [Declarative automation](https://docs.dagster.io/guides/automate/declarative-automation) | You want Dagster to decide when to materialise based on asset freshness and upstream changes |

Schedules and sensors are defined in `definitions.py` alongside the existing assets. See the [Dagster automation docs](https://docs.dagster.io/guides/automate) for full examples, and `dbt_packages/optimist/data-instructions.md` for guidance on choosing the right approach for your sources.

---

## Scaling up

The Optimist runs entirely on a local machine. When you're ready for team scale, the goal is to change a config flag — not rewrite your pipelines. The pipelines, dbt models, and orchestration logic you build on the Optimist are designed to carry forward unchanged.

The **Falcon** tier (on the roadmap) formalises this: switching `vessel: optimist` to `vessel: falcon` in `datavloot.yml` moves your platform to production-grade lakehouse storage on infrastructure of your choice, without starting over.

In the meantime, the Optimist's individual components are independently portable:

| Step | What changes | What stays the same |
|---|---|---|
| **Cloud VM** | Move the whole platform to a VPS or cloud VM | Nothing — runs identically |
| **Cloud storage** | Point DuckLake at S3, GCS, or Azure Blob instead of a local file | All dbt models and Dagster assets |
| **Cloud warehouse** | Swap `dbt-duckdb` for `dbt-snowflake`, `dbt-bigquery`, etc. | All models and macros (mostly portable SQL) |

See [datavloot.com/#fleet](https://datavloot.com/#fleet) for the full vessel roadmap.

---

## Using the dbt package in an existing project

If you already have a dbt project and only want the standardized macros, install the package via `dbt deps`:

```yaml
# packages.yml
packages:
  - git: "https://gitlab.com/datavloot/datavloot-toolkit.git"
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

Versions below are what the NOAA example project was built and tested on. Newer patch releases generally work; minor/major upgrades may require changes.

| Package | Tested version |
|---|---|
| Python | ≥3.10, <3.14 |
| dagster | 1.13.6 |
| dagster-dbt | 0.29.6 |
| dbt-core | 1.11.11 |
| dbt-duckdb | 1.10.1 |
| dlt | 1.28.0 |
| duckdb | 1.5.3 |
| ducklake | 0.1.1 |
| elementary-data | 0.24.0 |
| marimo | 0.23.9 |
