# datavloot-toolkit

Two things ship from this repo: the `optimist` dbt package (standardized macros, conventions and
model templates) and the `datavloot` Python package (the CLI, the lake storage, the Crows Nest
and the project templates). Designed to be used by AI agents (crew) following instructions from
a human user (captain).

---

## Repo layout

```
dbt/optimist/                              # the installable dbt package
├── macros/
│   ├── source/                            # stage_source, add_audit_columns
│   └── business/                          # build_dimension, build_fact, build_dataset,
│                                           # build_dim_date, build_dim_time, generate_surrogate_key,
│                                           # generate_date_key, dim_key_name
├── models/
│   └── source/                            # _sources.yml and _schema.yml templates
docs/                                      # reference documentation
datavloot_platform/                         # the datavloot Python package
├── cli.py                                 # datavloot new | demo | start | launch
├── storage.py                             # how dbt, dlt, assets and notebooks attach the lake
├── crowsnest/                             # the Crows Nest dashboard (FastAPI + a prebuilt frontend)
└── templates/
    ├── scaffold/                          # new-project template (served via `datavloot new`)
    └── demo/                              # NOAA worked example (served via `datavloot demo`)
deploy/
├── compose/                               # the Falcon: the platform on Docker Compose
└── thalassa/                              # OpenTofu module for a Falcon VM on Thalassa Cloud
```

Note: `dim_date`/`dim_time` ship as macros (`build_dim_date`/`build_dim_time`), not models — there
is no `dbt/optimist/models/business/` anymore. Every consuming project owns its own
`dim_date.sql`/`dim_time.sql` calling those macros (already scaffolded in both templates), which
is what makes the date range and time grain configurable per project.

---

## If you are building models in a consuming project

You are in the wrong repo. Run `datavloot new <path>` to scaffold a new consuming project, then follow the `data-instructions.md` inside it.

---

## If you are modifying the toolkit

The captain will tell you which of these applies:

- **Adding a macro** — create the `.sql` file under `macros/source/` or `macros/business/`, then document it in `docs/`
- **Editing source templates** — `_sources.yml`/`_schema.yml` blank templates are in `dbt/optimist/models/source/`. Dimension/fact/dataset config templates live in each project template instead (`datavloot_platform/templates/scaffold/models/business/`) — there's no package-level equivalent, since business-layer models are entirely project-owned
- **Editing `dim_date`/`dim_time`** — they're macros, not models: `macros/business/build_dim_date.sql` / `build_dim_time.sql`. A change here needs the same change made to both project templates' `dim_date.sql`/`dim_time.sql`/`_dim_configs.yml` only if the column shape changes — the macro call itself (`{{ optimist.build_dim_date() }}`) doesn't need to change for most edits
- **Updating the agent guide** — workflow changes go in `dbt/optimist/data-instructions.md`; it is the single source of truth for all consuming projects. The `data-instructions.md` inside each project template contains only project identity and a reference to the package doc — do not duplicate conventions there

---

## Conventions

- Macros are namespaced as `optimist.<macro_name>` in consuming projects
- All business-layer config lives in YAML `meta` blocks — no logic in SQL files
- Source-layer models follow the double-underscore pattern: `stg_<source>__<table>`
- Column documentation (dbt docs) lives at the model level; macro selection config lives inside `meta`
- Modelling conventions (Kimball, materialization, CTE structure) live in `dbt/optimist/data-instructions.md` and ship with the package — consuming projects reference `dbt_packages/optimist/data-instructions.md`
