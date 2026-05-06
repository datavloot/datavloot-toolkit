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
