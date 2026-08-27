# Getting started

optimist-toolkit is a shared dbt package that provides standardized macros, conventions, and
model templates to be reused across Optimist dbt projects.

---

## Installation

Add the package to your project's `packages.yml`:

```yaml
packages:
  - git: "https://gitlab.com/datavloot/datavloot-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: 0.1.x       # latest 0.1 patch; pin to a tag (e.g. 0.1.0) in production
```

Then install it:

```bash
dbt deps
```

### Keeping the package up to date

`revision: 0.1.x` is a moving branch that always points at the newest `0.1.*` release, so it
picks up patch releases without you editing `packages.yml`. Pin to an exact tag (`0.1.0`)
instead if you would rather bump deliberately. New releases where the "x" part of the tag is upgraded will never contain breaking changes. You are required to manually change the revision to something like 0.2.x when a breaking change is introduced and you will have to adjust your project to deal with it. The breaking change and how to handle it will always come with instructions for your agent of choice. 

On the first `dbt deps`, dbt
writes a `package-lock.yml` recording the exact commit it resolved:

```yaml
- git: https://gitlab.com/datavloot/datavloot-toolkit.git
  name: optimist
  revision: <>
  subdirectory: dbt/optimist
```

From then on, `dbt deps` reinstalls that pinned commit — it does **not** re-check the
branch. Whether you get new patch releases automatically is therefore decided by what you do
with that file:

| | Commit `package-lock.yml` | Add it to `.gitignore` |
|---|---|---|
| **Getting a new patch** | `dbt deps --upgrade`, then commit the updated lock | automatic on the next `dbt deps` |
| **Reproducibility** | everyone and CI build the identical commit | devs and CI can resolve different patches |
| **Audit trail** | version changes appear in git history | no record of which version was used |

The scaffold in `datavloot new` deliberately ships neither choice, so the file lands wherever
your project's conventions put it.

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
| `generate_surrogate_key` | MD5 surrogate key over a list of columns | [Business layer](business-layer.md) |
| `dim_date` | Shared date dimension (2015–2035, configurable) | [Business layer](business-layer.md) |
| `dim_time` | Shared time dimension (minute granularity) | [Business layer](business-layer.md) |

---

## Running the pipeline

The toolkit uses [Dagster](https://dagster.io) to orchestrate assets.

Activate the project virtual environment first so `dbt` and `dagster` are on your PATH:

```bash
source .venv/bin/activate
```

Then generate a compiled dbt manifest (Dagster needs this to discover your models) and start the server:

```bash
dbt parse
dagster dev
```

Open [http://localhost:3000](http://localhost:3000). The **Asset Catalog** lists every asset in
your pipeline — ingestion assets (dlt pipelines or plain Dagster assets) alongside all dbt source
and business models.

Materialise assets in dependency order: raw ingestion first, then dbt. To re-run only the dbt
transformation layer without re-loading source data, select the dbt assets and click
**Materialize selected**.

The **Runs** tab shows logs for every execution. dbt test failures and Elementary data quality
alerts surface here as asset check failures alongside the asset metadata.

---

## Querying results

All business-layer tables land in the `main_business` schema of your DuckDB database file.

### Install the DuckDB CLI

```bash
curl -Lo /tmp/duckdb.zip https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip /tmp/duckdb.zip -d ~/.local/bin/
chmod +x ~/.local/bin/duckdb
```

### Open the database

```bash
duckdb path/to/your.duckdb
```

### Useful shell commands

```sql
-- List all tables across all schemas
SHOW ALL TABLES;

-- Inspect a table's columns
DESCRIBE main_business.dim_<entity>;

-- Count rows in a fact table
SELECT COUNT(*) FROM main_business.fct_<event>;
```

Type `.quit` to exit.

### Schema layout

| Schema | Contents |
|---|---|
| `main` | Raw tables loaded by ingestion assets |
| `main_business` | Dimension and fact tables built by dbt |
| `main_elementary` | Elementary data quality metadata |

The default profile uses a relative path for the database file — run the `duckdb` command from
your project directory, or supply the full path.
