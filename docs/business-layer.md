# Business layer

The business layer contains analytics-ready models built on top of the source layer.
Models here apply business logic, generate surrogate keys, and deduplicate where needed.
No raw source references (`source()`) belong here — always read from `ref()` or from
an inline CTE.

---

## Naming convention

| Model type | Pattern | Example |
|---|---|---|
| Dimension | `dim_<entity>` | `dim_vessel`, `dim_port`, `dim_date` |
| Fact | `fct_<event>` | `fct_journey`, `fct_port_call` |

---

## Quickstart

Dimension configs live in a single file — [`models/business/_dim_configs.yml`](../dbt/optimist/models/business/_dim_configs.yml).
The model SQL file only needs the data source and a bare macro call.

**Step 1 — add an entry to `_dim_configs.yml`:**

```yaml
models:
  - name: dim_vessel
    description: "Vessel dimension."
    meta:
      source_model: stg_harbor__vessels
      surrogate_key:
        columns: [vessel_id]
        alias: dim_vessel_key
      columns:
        - vessel_id
        - name
        - vessel_type
        - flag_country
        - length_m
```

**Step 2 — create the model SQL file:**

```sql
-- models/business/dim_vessel.sql
{{ optimist.build_dimension() }}
```

The macro reads `model.meta` at compile time — no config needed in the SQL file.

---

## `build_dimension` — source options

Exactly one source option must be set in the `_dim_configs.yml` meta block.

### Option 1 — `source_model`: staged source

Reads from a source-layer model via `ref()`. The standard path for entity dimensions.

```yaml
# _dim_configs.yml
- name: dim_vessel
  meta:
    source_model: stg_harbor__vessels
    surrogate_key:
      columns: [vessel_id]
    columns: [vessel_id, name, vessel_type, flag_country, length_m]
```

```sql
-- dim_vessel.sql
{{ optimist.build_dimension() }}
```

---

### Option 2 — `source_seed`: seed file

Reads from a dbt seed via `ref()`. Ideal for small static lookup tables in `seeds/`.

```yaml
# _dim_configs.yml
- name: dim_country
  meta:
    source_seed: country_codes
    surrogate_key:
      columns: [iso_code]
    columns: [iso_code, country_name, region]
```

```sql
-- dim_country.sql
{{ optimist.build_dimension() }}
```

---

### Option 3 — `source_cte`: CTE in this file

References a CTE defined earlier in the model SQL file. The macro **continues the
existing CTE chain** instead of opening a new `WITH` block.

Use this for generated dimensions (date spines, time spines) or when the source
requires multi-step preparation before the dimension logic.

```yaml
# _dim_configs.yml
- name: dim_vessel
  meta:
    source_cte: enriched_vessels
    surrogate_key:
      columns: [vessel_id]
    columns: [vessel_id, name, vessel_type, flag_country, length_m, journey_count]
```

```sql
-- dim_vessel.sql
with enriched_vessels as (

    select
        v.*,
        count(j.journey_id) as journey_count
    from {{ ref('stg_harbor__vessels') }} v
    left join {{ ref('stg_harbor__journeys') }} j using (vessel_id)
    group by all

)

{{ optimist.build_dimension() }}
```

The built-in `dim_date` and `dim_time` use this pattern — the generation spine is
a named CTE in the SQL file, the config in `_dim_configs.yml` drives the output.

---

## `build_dimension` — full config reference

```yaml
# In _dim_configs.yml, under the model's meta: block.
# Exactly one of these:
source_model: <model_name>
source_seed:  <seed_name>
source_cte:   <cte_name>

# Required
surrogate_key:
  columns: [<col>, ...]       # columns to hash into the key
  alias: <model_name>_key     # optional; defaults to <model_name>_key

# Optional — remove if source is already unique per natural key
deduplicate:
  partition_by: [<col>, ...]
  order_by: _loaded_at desc   # defaults to _loaded_at desc if omitted

# Optional — remove to select all columns
# When using source_model or source_seed, staging audit columns
# (_loaded_at, _source_name, _source_table) are always excluded automatically.
columns:
  - <col>
  - <col>
```

A blank annotated template is at [`models/business/_dim_config_template.yml`](../dbt/optimist/models/business/_dim_config_template.yml).

---

## `build_fact`

Fact models represent events at a defined grain (one row per journey, port call, etc.).
`build_fact` mirrors `build_dimension` in structure — same source options, same
`model.meta` config, same surrogate key and deduplication handling — and adds
`dimensions` to resolve foreign keys to surrogate keys via LEFT JOINs.

### Quickstart

**Step 1 — add an entry to `_fct_configs.yml`:**

```yaml
models:
  - name: fct_journey
    description: "One row per completed sailing journey."
    meta:
      source_model: stg_harbor__journeys
      surrogate_key:
        columns: [journey_id]
        alias: fct_journey_key
      dimensions:
        - dim: dim_vessel
          fk: vessel_id
          key: dim_vessel_key
        - dim: dim_date
          fk: departure_at
          dim_fk: date_day
          fk_cast: date
          key: dim_date_key
          alias: departure_date_key
        - dim: dim_date
          fk: arrival_at
          dim_fk: date_day
          fk_cast: date
          key: dim_date_key
          alias: arrival_date_key
      columns:
        - journey_id
        - vessel_id
        - distance_nm
        - crew_count
        - duration_hours
```

**Step 2 — create the model SQL file:**

```sql
-- models/business/fct_journey.sql
{{ optimist.build_fact() }}
```

This generates:

```sql
with source as (
    select * from stg_harbor__journeys
),
base as (
    select * from source
),
joined as (
    select
        base.*,
        _dim_0.dim_vessel_key,
        _dim_1.dim_date_key as departure_date_key,
        _dim_2.dim_date_key as arrival_date_key
    from base
    left join dim_vessel _dim_0
        on base.vessel_id = _dim_0.vessel_id
    left join dim_date _dim_1
        on cast(base.departure_at as date) = _dim_1.date_day
    left join dim_date _dim_2
        on cast(base.arrival_at as date) = _dim_2.date_day
),
final as (
    select
        md5(...)              as fct_journey_key,
        dim_vessel_key,
        departure_date_key,
        arrival_date_key,
        journey_id,
        vessel_id,
        distance_nm,
        crew_count,
        duration_hours,
        current_timestamp     as _loaded_at
    from joined
)
select * from final
```

---

### Source options

Same three options as `build_dimension` — `source_model`, `source_seed`, `source_cte`.
Use `source_cte` when the source needs preparation before joining (e.g. casting
timestamps, pre-aggregating):

```sql
-- fct_journey.sql
with prepared as (

    select
        *,
        date_diff('hour', departure_at, arrival_at) as duration_hours
    from {{ ref('stg_harbor__journeys') }}

)

{{ optimist.build_fact() }}
```

```yaml
# _fct_configs.yml
- name: fct_journey
  meta:
    source_cte: prepared
    ...
```

---

### Dimension relationships

Each entry in `dimensions` generates one LEFT JOIN and pulls the dim's surrogate key
into the fact. The same dimension can appear multiple times — each gets a unique
internal join alias automatically.

| Key | Required | Default | Description |
|---|---|---|---|
| `dim` | yes | — | Dimension model name (used in `ref()`) |
| `fk` | yes | — | FK column in the source |
| `dim_fk` | no | same as `fk` | Matching column in the dim (when names differ) |
| `fk_cast` | no | none | SQL type to cast the FK to before joining |
| `key` | no | `<dim>_key` | Surrogate key column to pull from dim |
| `alias` | no | same as `key` | Output column name in the fact |

---

### `build_fact` — full config reference

```yaml
# In _fct_configs.yml, under the model's meta: block.
# Exactly one of these:
source_model: <model_name>
source_seed:  <seed_name>
source_cte:   <cte_name>

# Required — defines the grain
surrogate_key:
  columns: [<col>, ...]
  alias: <model_name>_key     # optional; defaults to <model_name>_key

# Optional — one entry per dimension join
dimensions:
  - dim: <dim_model>
    fk: <fk_column>
    dim_fk: <dim_column>      # default: same as fk
    fk_cast: <sql_type>       # default: no cast
    key: <dim_surrogate_key>  # default: <dim>_key
    alias: <output_name>      # default: same as key

# Optional — remove if source is already unique per grain
deduplicate:
  partition_by: [<col>, ...]
  order_by: _loaded_at desc

# Optional but recommended — explicit measure columns
# Omitting selects all source columns (dim keys and staging audit columns excluded).
columns:
  - <grain_column>
  - <measure_column>
```

A blank annotated template is at [`models/business/_fct_config_template.yml`](../dbt/optimist/models/business/_fct_config_template.yml).

---

## `generate_surrogate_key`

Used internally by `build_dimension`, but also available standalone for custom models.
Hashes a list of columns into a single MD5 string. NULLs coalesce to empty string.

```sql
select
    {{ optimist.generate_surrogate_key(['journey_id', 'waypoint_id']) }} as journey_waypoint_key,
    ...
from my_table
```

---

## Shared dimensions

The toolkit ships two ready-to-use dimensions that consuming projects inherit automatically:

| Model | Rows | Key column | Notes |
|---|---|---|---|
| `dim_date` | ~7 600 (2015–2035) | `dim_date_key` | Range configurable via `dim_date_start` / `dim_date_end` vars |
| `dim_time` | 1 440 | `dim_time_key` | Minute granularity, full 24-hour period |
