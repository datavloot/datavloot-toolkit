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

Ask the captain: how recently should each source have received data? Configure `freshness`
and `loaded_at_field` accordingly (see Step 7 — Data quality).

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

After creating each staging model, ask the captain about data quality expectations — see **Step 7**.

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

After creating each dimension, ask the captain about data quality expectations — see **Step 7**.

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

After creating each fact, ask the captain about data quality expectations — see **Step 7**.

Config template: `models/business/facts/_fct_configs.yml` (see header comments)
Full reference: `dbt_packages/optimist/models/business/_fct_config_template.yml`
Docs: `dbt_packages/optimist/docs/business-layer.md`

### Step 6 — Document

Add `columns` entries with descriptions to every model in the relevant `_configs.yml` or
`_schema.yml`. Follow the pattern used in `dim_date` and `dim_time` inside
`dbt_packages/optimist/models/business/dimensions/_dim_configs.yml`.

### Step 7 — Data quality tests

After creating **each model**, ask the captain the following questions and configure tests
based on their answers. Do not skip this step — undocumented expectations become silent failures.

#### Questions to ask

| Topic | Question |
|---|---|
| Nulls | Which columns must always have a value? |
| Uniqueness | Which column (or combination) uniquely identifies a row? |
| Accepted values | Are there columns with a fixed set of valid values? (e.g. status, category, type) |
| Dates in the future | Are there date or timestamp columns that can never be ahead of today? |
| Dates in the past | Are there date columns that should never be before a certain cutoff? |
| Numeric ranges | Are there numeric columns with expected bounds? (e.g. amounts > 0, percentages 0–100) |
| Referential integrity | Should any FK column always resolve to a row in another model? |
| Freshness *(sources only)* | How long after an expected load is a missing update considered a warning? An error? |

#### Generic tests — in `_schema.yml`, `_dim_configs.yml`, or `_fct_configs.yml`

```yaml
columns:
  - name: order_id
    data_tests:
      - not_null
      - unique

  - name: status
    data_tests:
      - not_null
      - accepted_values:
          values: ['pending', 'confirmed', 'cancelled']

  - name: dim_customer_key
    data_tests:
      - not_null
      - relationships:
          to: ref('dim_customer')
          field: dim_customer_key
```

#### Singular tests — for custom logic, one SQL file per test in `tests/`

A singular test fails if it returns any rows. Name the file to make the assertion obvious.

```sql
-- tests/assert_fct_order_order_date_not_in_future.sql
select *
from {{ ref('fct_order') }}
where order_date > current_date
```

```sql
-- tests/assert_fct_order_amount_positive.sql
select *
from {{ ref('fct_order') }}
where amount <= 0
```

```sql
-- tests/assert_dim_date_no_gaps.sql
-- Fails if any consecutive pair of dates is more than 1 day apart.
select date_day
from {{ ref('dim_date') }}
where date_day - lag(date_day) over (order by date_day) > interval '1 day'
```

#### Source freshness — in `models/source/_sources.yml`

```yaml
sources:
  - name: harbor
    loaded_at_field: ingested_at      # column dbt checks to evaluate freshness
    freshness:
      warn_after:  {count: 12, period: hour}
      error_after: {count: 24, period: hour}
    tables:
      - name: vessels
        # Override freshness per table if this table updates less frequently:
        # freshness:
        #   warn_after:  {count: 7, period: day}
        #   error_after: {count: 14, period: day}
```

Run `dbt source freshness` to check all configured sources.

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
│   ├── _sources.yml                  # raw source definitions + freshness — edit here
│   ├── _schema.yml                   # staging model docs and tests — edit here
│   └── stg_<source>__<table>.sql     # one file per source table
└── business/
    ├── dimensions/
    │   ├── _dim_configs.yml          # all dimension configs and tests — edit here
    │   └── dim_<entity>.sql          # one file per dimension
    └── facts/
        ├── _fct_configs.yml          # all fact configs and tests — edit here
        └── fct_<event>.sql           # one file per fact
tests/
└── assert_<model>_<description>.sql  # one file per custom singular test
```

---

## When to pause and ask the captain

- Before creating any model: confirm the grain (one row = one ___?)
- Before joining a dimension to a fact: confirm which column maps to which
- When a source column name is ambiguous: ask, don't assume
- When a business rule could go multiple ways: surface the options, let the captain decide
