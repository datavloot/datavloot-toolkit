# [project-name]

A dbt project built on [optimist-toolkit](https://gitlab.com/mycelium4483613/optimist-toolkit).

---

## Captain and crew

**Captain** — the human user who describes what they want to understand or measure.
**Crew** — AI agents (e.g. Claude) who translate that into working dbt models.

As crew, your job is to ask the right questions and then build exactly what the captain describes,
following the conventions in this file. Do not build speculatively — confirm understanding before
creating any files.

---

## Pre-flight: what to ask the captain first

Before writing any code, confirm:

1. What business process or data do they want to model?
2. What source system(s) does the data come from — database, schema, and table names?
3. What questions should the data answer? (This drives which dimensions and facts to build.)
4. What is the grain of each fact? (One row = one ___?)

---

## Workflow

Follow this order strictly. Each step depends on the previous.

### Step 1 — Define sources

Edit `models/source/_sources.yml`. Add one source block per source system, with one table
entry per raw table the captain wants to use.

Full template and freshness config options: `models/source/_sources.yml`

### Step 2 — Stage sources

For each raw table, create a staging model.

**`models/source/stg_<source>__<table>.sql`**:
```sql
{{ optimist.stage_source('<source>', '<table>') }}
```

Then add a model entry to `models/source/_schema.yml` with column descriptions and `data_tests`.

**Incremental loading** — source models default to `incremental` materialization, meaning only new
rows are processed on each run. For this to work correctly, every staging model needs two things:

1. A `unique_key` config so dbt upserts instead of appending:
   ```sql
   {{ config(unique_key='<natural_key>') }}
   {{ optimist.stage_source('<source>', '<table>', incremental_column='<updated_at_col>') }}
   ```
2. Ask the captain: which column marks when a row was last updated? (e.g. `updated_at`, `modified_at`, `ingested_at`)

If no reliable timestamp exists in the source, ask the captain whether to use `view` materialization
for this model instead (always fresh, no incremental filter needed), by adding
`{{ config(materialized='view') }}` before the macro call.

**Deduplication** — ask the captain: does this source emit multiple versions of the same record
(e.g. a CDC feed or append-only log with updates)? If yes, add `deduplicate_by` with the natural
key column(s) and add a `unique` test on that column in `_schema.yml`:

```sql
{{ optimist.stage_source('<source>', '<table>', deduplicate_by=['<natural_key>'], order_by='<updated_at_col> desc') }}
```

```yaml
# models/source/_schema.yml
- name: <natural_key>
  description: ""
  data_tests:
    - not_null
    - unique     # enforces the deduplication guarantee
```

Reference: `dbt_packages/optimist/docs/source-layer.md`

### Step 3 — Add seed data (optional)

If the captain needs mapping tables, code lookups, or other small static reference data that
doesn't exist in any source system, add it as a seed before building dimensions.

1. Add a CSV file to `seeds/<seed_name>.csv`
2. Add an entry to `seeds/_seeds.yml` with descriptions and `data_tests`
3. Run `dbt seed` to load it into the warehouse

Seeds can then be used as a dimension source via `source_seed: <seed_name>` in `_dim_configs.yml`.

Guidance on when seeds are appropriate: `seeds/how_to.md`

### Step 4 — Build dimensions

For each entity the captain cares about (person, product, location, vessel, etc.):

1. Add a config block to `models/business/dimensions/_dim_configs.yml`
2. Create `models/business/dimensions/dim_<entity>.sql`:
   ```sql
   {{ optimist.build_dimension() }}
   ```

`dim_date` and `dim_time` ship with the toolkit — reference them with `ref('dim_date')` and
`ref('dim_time')` without creating new models.

Config template: `models/business/dimensions/_dim_configs.yml` (see header comments)
Full reference: `dbt_packages/optimist/models/business/_dim_config_template.yml`
Docs: `dbt_packages/optimist/docs/business-layer.md`

### Step 5 — Build facts

For each event or transaction the captain wants to measure:

1. Add a config block to `models/business/facts/_fct_configs.yml`
2. Create `models/business/facts/fct_<event>.sql`:
   ```sql
   {{ optimist.build_fact() }}
   ```

Config template: `models/business/facts/_fct_configs.yml` (see header comments)
Full reference: `dbt_packages/optimist/models/business/_fct_config_template.yml`
Docs: `dbt_packages/optimist/docs/business-layer.md`

### Step 6 — Document

Add `columns` entries with descriptions to every model in the relevant `_configs.yml` or
`_schema.yml`. Follow the pattern used in `dim_date` and `dim_time` inside
`dbt_packages/optimist/models/business/dimensions/_dim_configs.yml`.

---

## Naming conventions

| Layer | Pattern | Example |
|---|---|---|
| Staging | `stg_<source>__<table>` | `stg_harbor__vessels` |
| Dimension | `dim_<entity>` | `dim_vessel` |
| Fact | `fct_<event>` | `fct_journey` |
| Surrogate key | `<model>_key` | `dim_vessel_key`, `fct_journey_key` |

- Double underscore (`__`) separates the source name from the table name in staging models.
- Dimension entities are singular nouns (`dim_vessel`, not `dim_vessels`).
- Fact events are noun phrases (`fct_orders`, `fct_port_calls`).
- All config lives in `_configs.yml` files — no logic in SQL files.

---

## File map

```
seeds/
├── _seeds.yml                        # seed descriptions and data_tests — edit here
├── how_to.md                         # guidance on when to use seeds
└── <seed_name>.csv                   # one file per seed
models/
├── source/
│   ├── _sources.yml                  # raw source definitions — edit here
│   ├── _schema.yml                   # staging model docs — edit here
│   └── stg_<source>__<table>.sql     # one file per source table
└── business/
    ├── dimensions/
    │   ├── _dim_configs.yml          # all dimension configs — edit here
    │   └── dim_<entity>.sql          # one file per dimension
    └── facts/
        ├── _fct_configs.yml          # all fact configs — edit here
        └── fct_<event>.sql           # one file per fact
```

---

## When to pause and ask the captain

- Before creating any model: confirm the grain (one row = one ___?)
- Before joining a dimension to a fact: confirm which column maps to which
- When a source column name is ambiguous: ask, don't assume
- When a business rule could go multiple ways: surface the options, let the captain decide
