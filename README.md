# optimist-toolkit

A shared dbt package providing standardized macros, conventions, and model templates
for Optimist dbt projects. Install via `dbt deps` and get consistent source staging,
audit columns, and schema naming across all projects.

## Documentation

- [Getting started](docs/getting-started.md) — installation and project structure
- [Source layer](docs/source-layer.md) — auto-generate staging models with audit columns

## Quick example

Add one line to any source model and get a fully staged table with all columns and audit metadata:

```sql
-- models/source/stg_harbor__vessels.sql
{{ optimist.stage_source('harbor', 'vessels') }}
```
