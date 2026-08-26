# noaa

A dbt project built on [optimist-toolkit](https://gitlab.com/datavloot/datavloot-toolkit),
demonstrating AIS vessel tracking enriched with marine weather data for the port of Guam.

See `dbt_packages/optimist/data-instructions.md` for the full workflow, naming conventions, modelling
conventions, and captain/crew guide. Run `dbt deps` if the file is not yet present.

---

## Project context

- **Sources**: NOAA AIS broadcasts (CSV → DuckDB via Dagster asset) and Open-Meteo atmospheric hourly
  (dlt pipeline — incremental by date cursor)
- **Warehouse**: DuckDB (`noaa.duckdb`)
- **Orchestration**: Dagster via `noaa_platform/`; run `dagster dev` from the project root
- **Source subfolders**: `source/ais/` (incremental) and `source/open_meteo/` (ephemeral) —
  materializations set by folder in `dbt_project.yml`
