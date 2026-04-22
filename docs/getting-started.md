# Getting started

optimist-toolkit is a shared dbt package that provides standardized macros, conventions, and
model templates to be reused across Optimist dbt projects.

---

## Installation

Add the package to your project's `packages.yml`:

```yaml
packages:
  - git: "https://gitlab.com/mycelium4483613/optimist-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: main        # pin to a tag or commit SHA in production
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
| `generate_surrogate_key` | MD5 surrogate key over a list of columns | [Business layer](business-layer.md) |
| `dim_date` | Shared date dimension (2015–2035, configurable) | [Business layer](business-layer.md) |
| `dim_time` | Shared time dimension (minute granularity) | [Business layer](business-layer.md) |
| `generate_schema_name` | Schema naming without target prefix | — |
