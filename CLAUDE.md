# optimist-toolkit

A shared dbt package providing standardized macros, conventions, and model templates for dbt projects.
Designed to be used by AI agents (crew) following instructions from a human user (captain).

---

## Repo layout

```
dbt/optimist/           # the installable dbt package
├── macros/
│   ├── source/         # stage_source, add_audit_columns
│   └── business/       # build_dimension, build_fact, generate_surrogate_key
├── models/
│   ├── source/         # _sources.yml and _schema.yml templates
│   └── business/       # dim/fct config templates + dim_date, dim_time
docs/                   # reference documentation
scaffold/               # starting point for a new consuming project
```

---

## If you are building models in a consuming project

You are in the wrong repo. The `scaffold/` directory is a copy-paste template for a new consuming project. Copy it, run `dbt deps`, then follow the `CLAUDE.md` in that project.

---

## If you are modifying the toolkit

The captain will tell you which of these applies:

- **Adding a macro** — create the `.sql` file under `macros/source/` or `macros/business/`, then document it in `docs/`
- **Editing a config template** — `_dim_config_template.yml` and `_fct_config_template.yml` are in `dbt/optimist/models/business/`; source templates are in `dbt/optimist/models/source/`
- **Editing built-in dimensions** — configs in `dbt/optimist/models/business/dimensions/_dim_configs.yml`, SQL alongside
- **Updating the scaffold** — keep `scaffold/CLAUDE.md` in sync with any workflow changes; it is the agent guide for all consuming projects

---

## Conventions

- Macros are namespaced as `optimist.<macro_name>` in consuming projects
- All business-layer config lives in YAML `meta` blocks — no logic in SQL files
- Source-layer models follow the double-underscore pattern: `stg_<source>__<table>`
- Column documentation (dbt docs) lives at the model level; macro selection config lives inside `meta`
