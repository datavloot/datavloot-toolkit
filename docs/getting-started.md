# Working in a project

To install Datavloot and create a project, follow [Installing](https://github.com/datavloot/datavloot-toolkit#installing)
in the README. This page is about what is in a project once it is there.

A project created with `datavloot new` is a dbt project with a Dagster layer around it. Its
models use the `optimist` dbt package, which provides standardized macros, conventions, and
model templates; the package has its own repository,
[dbt-datavloot-optimist](https://github.com/datavloot/dbt-datavloot-optimist).

---

## Installation

`datavloot new` writes the package into the project's `packages.yml`, pinned to the release this
toolkit was tested with, together with Elementary, which the Crows Nest's Data quality and
Catalog panels read:

```yaml
packages:
  - tarball: "https://codeload.github.com/datavloot/dbt-datavloot-optimist/tar.gz/refs/tags/0.1.1"
    name: optimist
  - package: elementary-data/elementary
    version: [">=0.25.0", "<0.26.0"]
```

Then install them, from the project folder:

```bash
uv run dbt deps
```

---

## Project structure

```
your-project/
└── models/
    ├── source/           # thin staging wrappers over raw sources
    │   ├── _sources.yml  # source definitions (scaffolded by datavloot new)
    │   ├── _schema.yml   # model docs and tests (scaffolded by datavloot new)
    │   └── stg_<source>__<table>.sql
    └── business/         # transformed, business-oriented models
```

`datavloot new` scaffolds the blank config templates for the `source/` layer,
`models/source/_sources.yml` and `models/source/_schema.yml`.

---

## Available features

| Feature | Description | Docs |
|---|---|---|
| `stage_source` | Auto-generate a source staging model with audit columns | [Source layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/source-layer.md) |
| `add_audit_columns` | Emit standard audit columns in any SELECT | [Source layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/source-layer.md) |
| `build_dimension` | Generate a dimension from a staged model, seed, or inline CTE | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `build_fact` | Generate a fact with dim joins and measures from config | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `build_dataset` | Flat, documented one-big-table output from a source you have already prepared (no surrogate key, no dimension joins) | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `generate_surrogate_key` | MD5 surrogate key over a list of columns | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `generate_date_key` | Integer `YYYYMMDD` key for joining to `dim_date` | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `build_dim_date` | Date dimension, called from the project's own `dim_date.sql` (2015–2035 by default, configurable) | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |
| `build_dim_time` | Time-of-day dimension at minute granularity, called from `dim_time.sql` | [Business layer](https://github.com/datavloot/dbt-datavloot-optimist/blob/main/docs/business-layer.md) |

---

## Running the pipeline

The toolkit uses [Dagster](https://dagster.io) to orchestrate assets.

Run the commands from the project folder with `uv run`, which uses the project's own
environment. (Or activate it first, with `source .venv/bin/activate` on Linux and macOS or
`.venv\Scripts\activate` on Windows, and leave out `uv run`.)

Generate a compiled dbt manifest (Dagster needs this to discover your models) and start the
platform:

```bash
uv run dbt parse
uv run datavloot start      # Dagster and the Crows Nest; or `uv run dagster dev` for Dagster alone
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

### Windows asks whether Python may use public and private networks

With Marimo 0.26 or newer, which installs on Python 3.11 and up, opening a notebook no longer
brings up this question: Marimo's language servers now look for free ports on `127.0.0.1` only.

With an older Marimo (Python 3.10, or a project installed before 0.26), the first time a notebook
opens (from the Crows Nest or with `marimo edit`) Windows Defender Firewall can ask whether Python
may access public and private networks. **Choose Cancel**, or leave both boxes unticked. Dagster,
the Crows Nest and Marimo listen on `localhost` only, which the firewall does not block, so
everything keeps working. The question comes from Marimo, not from anything the toolkit opens: in
edit mode it looks for free ports for its language servers on all network interfaces, which is
enough for Windows to ask. Windows asks once per `python.exe`, so it can come back after
installing a new Python version. A project on Python 3.10 stays on Marimo 0.25; move it to
Python 3.11 or later and it gets Marimo 0.26, so the question no longer comes.

Whether Marimo asks or not, do not allow **public networks**. The rule would cover that
`python.exe` on every port, for good: anything it runs later on a network address is then
reachable from any Wi-Fi you join. That includes `marimo edit --no-token` with another `--host`
(a Python shell for anyone on that network) and `datavloot launch --host 0.0.0.0`, whose sign-in
is off on a laptop. If you allowed it, switch the rule off under *Windows Security → Firewall & network protection →
Allow an app through firewall*, or in an administrator PowerShell:

```powershell
Get-NetFirewallApplicationFilter | Where-Object Program -match 'python' | Get-NetFirewallRule |
  Where-Object { $_.Action -eq 'Allow' -and $_.Profile -match 'Public' } | Disable-NetFirewallRule
```

To show the Crows Nest to someone on your own network, open one port on the private profile for
the occasion instead, start the Crows Nest on all interfaces with a sign-in token
(`CROWSNEST_AUTH_TOKEN`, see the README), and remove the rule afterwards:

```powershell
New-NetFirewallRule -DisplayName "Crows Nest demo" -Direction Inbound -Protocol TCP -LocalPort 8080 -Profile Private -Action Allow
$env:CROWSNEST_AUTH_TOKEN = uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
uv run datavloot launch --host 0.0.0.0
# afterwards:
Remove-NetFirewallRule -DisplayName "Crows Nest demo"
```

### Windows blocks a DuckDB extension (Smart App Control)

On some Windows 11 laptops the platform stops working with a message like this:

> pythonw.exe - Ongeldige installatiekopie (Invalid image)
> `C:\Users\<you>\.duckdb\extensions\v<version>\windows_amd64\ducklake.duckdb_extension` is niet geschikt voor Windows of het bevat een fout (is not suitable for Windows or contains an error). […] Foutstatus (Error status) 0xc0e90002.

Windows Security can show "Smart App Control heeft een deel van deze app geblokkeerd" (Smart
App Control blocked part of this app). The lake cannot be attached, so nothing that reads or
writes it runs.

DuckDB downloads its extensions (such as `ducklake`) as DLLs into `~/.duckdb/extensions/` and
loads them into the Python process. They are not signed with a certificate Windows trusts, and
Smart App Control blocks unsigned code that has no cloud reputation. You cannot allow a single
file.

Smart App Control only exists on clean installs of Windows 11 22H2 and later. It can start in
evaluation mode, which Windows later switches on or off by itself. That can explain why the
platform runs fine a few times and then gets blocked.

The only fix is to turn Smart App Control off. Look in the Windows Security app
(*Windows-beveiliging* in Dutch), under *App & browser control*, at *Smart App Control*. The
feature keeps that English name in Dutch Windows too. Weigh it first: on older Windows builds it could not be turned
back on without reinstalling Windows. On an up-to-date Windows it can be turned on again later in
the same app, see the
[Microsoft FAQ](https://support.microsoft.com/en-us/topic/what-is-smart-app-control-285ea03d-fa88-4d56-882e-6698afdb7003).
Defender Antivirus, SmartScreen and the firewall are not affected by this setting.

On a laptop managed by your employer, ask IT first. They may block the setting, or have another
way to allow DuckDB extensions.

---

## Querying results

All data is in a DuckLake under `lake/`: the catalog in `lake/catalog.sqlite`, the tables as
Parquet files under `lake/data/`. The Crows Nest's SQL editor and the notebooks open it for you;
from Python, `datavloot_platform.storage.connect(read_only=True)` does the same (see "Where the
data lives" in the README).

### Install the DuckDB CLI

Use the same version as the `duckdb` package in your environment, not the latest release: the
toolkit holds DuckDB below 2.0 (`duckdb<2` in its own `pyproject.toml`, not your project's) until
the lake has been tried on it, and the latest CLI is 2.0.

```bash
V=$(uv run python -c "import duckdb; print(duckdb.__version__)")   # a 1.x, e.g. 1.5.6
curl -fLo /tmp/duckdb.zip https://github.com/duckdb/duckdb/releases/download/v$V/duckdb_cli-linux-amd64.zip
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
