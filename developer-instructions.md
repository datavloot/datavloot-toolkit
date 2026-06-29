# optimist-toolkit

A shared dbt package providing standardized macros, conventions, and model templates for dbt projects.
Designed to be used by AI agents (crew) following instructions from a human user (captain).

---

## Repo layout

```
dbt/optimist/                              # the installable dbt package
├── macros/
│   ├── source/                            # stage_source, add_audit_columns
│   └── business/                          # build_dimension, build_fact, generate_surrogate_key
├── models/
│   ├── source/                            # _sources.yml and _schema.yml templates
│   └── business/                          # dim/fct config templates + dim_date, dim_time
docs/                                      # reference documentation
datavloot_platform/templates/scaffold/      # new-project template (served via `optimist new`)
datavloot_platform/templates/demo/          # NOAA worked example (served via `optimist demo`)
```

---

## If you are building models in a consuming project

You are in the wrong repo. Run `optimist new <path>` to scaffold a new consuming project, then follow the `data-instructions.md` inside it.

---

## If you are modifying the toolkit

The captain will tell you which of these applies:

- **Adding a macro** — create the `.sql` file under `macros/source/` or `macros/business/`, then document it in `docs/`
- **Editing a config template** — `_dim_config_template.yml` and `_fct_config_template.yml` are in `dbt/optimist/models/business/`; source templates are in `dbt/optimist/models/source/`
- **Editing built-in dimensions** — configs in `dbt/optimist/models/business/dimensions/_dim_configs.yml`, SQL alongside
- **Updating the agent guide** — workflow changes go in `dbt/optimist/data-instructions.md`; it is the single source of truth for all consuming projects. The `data-instructions.md` inside each project template contains only project identity and a reference to the package doc — do not duplicate conventions there

---

## Conventions

- Macros are namespaced as `optimist.<macro_name>` in consuming projects
- All business-layer config lives in YAML `meta` blocks — no logic in SQL files
- Source-layer models follow the double-underscore pattern: `stg_<source>__<table>`
- Column documentation (dbt docs) lives at the model level; macro selection config lives inside `meta`
- Modelling conventions (Kimball, materialization, CTE structure) live in `dbt/optimist/data-instructions.md` and ship with the package — consuming projects reference `dbt_packages/optimist/data-instructions.md`
