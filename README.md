# optimist-toolkit

A shared dbt package providing standardized macros, conventions, and model templates
for dbt projects. Install via `dbt deps` for consistent source staging, surrogate keys,
dimension and fact generation, and audit columns across all projects.

Designed to be used by AI agents (crew) following instructions from a human user (captain).
See [CLAUDE.md](CLAUDE.md) for the agent guide.

---

## Starting a new project

Copy the `scaffold/` directory as the foundation for any new project using this toolkit:

```
scaffold/
├── CLAUDE.md                          # AI agent workflow guide (captain/crew model)
├── packages.yml                       # points to this toolkit
├── dbt_project.yml                    # project config with sensible defaults
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

- Loading a large raw dataset (3.2 M rows) into DuckDB as a source instead of a seed
- Staging with audit columns and deduplication
- Deriving arrival and departure events from raw position broadcasts using window functions
- Building `dim_vessel`, `dim_port`, and `fct_port_event` with toolkit macros
- Configuring data quality tests at every layer

The noaa project was set up using the optmist-toolkit, purely by giving claude the claude.md instructions and positioning oneself as a captain with no data engineering skills. In conversation.md, the conversation used to build the project can be followed in marp-presentation form.

See [noaa/README.md](noaa/README.md). 

---

## Documentation

- [Getting started](docs/getting-started.md) — installation and project structure
- [Source layer](docs/source-layer.md) — staging, deduplication, incremental loading, audit columns
- [Business layer](docs/business-layer.md) — dimensions, facts, surrogate keys, dimension joins

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

## Installation

Add to your project's `packages.yml`:

```yaml
packages:
  - git: "https://gitlab.com/mycelium4483613/optimist-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: main        # pin to a tag or commit SHA for reproducible builds
```

Then install:

```bash
dbt deps
```
