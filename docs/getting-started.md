# Getting started

optimist-toolkit is a shared dbt package that provides standardized macros, conventions, and
model templates to be reused across Optimist dbt projects.

---

## Installation

Add the package to your project's `packages.yml`:

```yaml
packages:
  - git: "https://github.com/datavloot/datavloot-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: 0.1.x       # latest 0.1 patch; pin to a tag (e.g. 0.1.0) in production
```

Then install it:

```bash
dbt deps
```

---

## Project structure

```
your-project/
└── models/
    ├── source/           # thin staging wrappers over raw sources
    │   ├── _sources.yml  # source definitions (copy from optimist-toolkit template)
    │   ├── _schema.yml   # model docs and tests (copy from optimist-toolkit template)
    │   └── stg_<source>__<table>.sql
    └── business/         # transformed, business-oriented models
```

Config templates for the `source/` layer are provided in the package at
`models/source/_sources.yml` and `models/source/_schema.yml`.

---

## Available features

| Feature | Description | Docs |
|---|---|---|
| `stage_source` | Auto-generate a source staging model with audit columns | [Source layer](source-layer.md) |
| `add_audit_columns` | Emit standard audit columns in any SELECT | [Source layer](source-layer.md) |
| `build_dimension` | Generate a dimension from a staged model, seed, or inline CTE | [Business layer](business-layer.md) |
| `build_fact` | Generate a fact with dim joins and measures from config | [Business layer](business-layer.md) |
| `build_dataset` | Flat, documented one-big-table output from a source you have already prepared (no surrogate key, no dimension joins) | [Business layer](business-layer.md) |
| `generate_surrogate_key` | MD5 surrogate key over a list of columns | [Business layer](business-layer.md) |
| `generate_date_key` | Integer `YYYYMMDD` key for joining to `dim_date` | [Business layer](business-layer.md) |
| `build_dim_date` | Date dimension, called from the project's own `dim_date.sql` (2015–2035 by default, configurable) | [Business layer](business-layer.md) |
| `build_dim_time` | Time-of-day dimension at minute granularity, called from `dim_time.sql` | [Business layer](business-layer.md) |

---

## Running the pipeline

The toolkit uses [Dagster](https://dagster.io) to orchestrate assets.

Activate the project's virtual environment first so `dbt` and `dagster` are on your PATH
(`source .venv/bin/activate` on Linux and macOS, `.venv\Scripts\activate` on Windows).

Then generate a compiled dbt manifest (Dagster needs this to discover your models) and start the
platform:

```bash
dbt parse
datavloot start      # Dagster and the Crows Nest; or `dagster dev` for Dagster alone
```

Open [http://localhost:3000](http://localhost:3000) for Dagster, or the Crows Nest at
[http://localhost:8080](http://localhost:8080). The **Asset Catalog** lists every asset in
your pipeline — ingestion assets (dlt pipelines or plain Dagster assets) alongside all dbt source
and business models.

Materialise assets in dependency order: raw ingestion first, then dbt. To re-run only the dbt
transformation layer without re-loading source data, select the dbt assets and click
**Materialize selected**.

The **Runs** tab shows logs for every execution. dbt test failures and Elementary data quality
alerts surface here as asset check failures alongside the asset metadata.

---

## Querying results

All data is in a DuckLake under `lake/`: the catalog in `lake/catalog.sqlite`, the tables as
Parquet files under `lake/data/`. The Crows Nest's SQL editor and the notebooks open it for you;
from Python, `datavloot_platform.storage.connect(read_only=True)` does the same (see "Where the
data lives" in the README).

### Install the DuckDB CLI

Use the same version as the `duckdb` package in your environment, not the latest release: the
toolkit holds DuckDB below 2.0 (`duckdb<2` in `pyproject.toml`) until the lake has been tried on
it, and the latest CLI is 2.0.

```bash
V=$(python -c "import duckdb; print(duckdb.__version__)")   # a 1.x, e.g. 1.5.6
curl -Lo /tmp/duckdb.zip https://github.com/duckdb/duckdb/releases/download/v$V/duckdb_cli-linux-amd64.zip
unzip /tmp/duckdb.zip -d ~/.local/bin/
chmod +x ~/.local/bin/duckdb
```

On macOS use `duckdb_cli-osx-universal.zip`, on Windows `duckdb_cli-windows-amd64.zip`.

### Open the lake

From the project directory, read-only, so it can stay open while a pipeline runs:

```bash
duckdb -cmd "ATTACH 'ducklake:sqlite:lake/catalog.sqlite' AS <project> (DATA_PATH 'lake/data/', OVERRIDE_DATA_PATH true, READ_ONLY); USE <project>;"
```

### Useful shell commands

```sql
-- List all tables across all schemas
SHOW ALL TABLES;

-- Inspect a table's columns
DESCRIBE <project>_business.dim_<entity>;

-- Count rows in a fact table
SELECT COUNT(*) FROM <project>_business.fct_<event>;
```

Type `.quit` to exit.

### Schema layout

Production (what Dagster builds, dbt's `prod` target) and development (dbt by hand, the default
`dev` target) live side by side in the same lake:

| Schema | Contents |
|---|---|
| The schema your ingestion writes to (dlt's `dataset_name`, e.g. `source`) | Raw tables loaded by ingestion assets |
| `<project>_source`, `<project>_business` | Staging, dimension and fact tables built by Dagster |
| `<project>_seeds` | Seeds |
| `<project>_elementary` | Elementary data quality metadata |
| `dev_source`, `dev_business`, … | The same, from dbt runs by hand |
