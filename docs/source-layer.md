# Source layer

The source layer contains thin staging models that sit directly on top of raw source tables.
Each model selects all available columns from the source and appends standard audit columns.
No business logic lives here — that belongs in the business layer.

---

## Naming convention

Source models follow the dbt standard double-underscore convention:

```
stg_<source_name>__<table_name>.sql
```

Examples: `stg_harbor__vessels.sql`, `stg_harbor__journeys.sql`

---

## Quickstart

**1. Define your source in `models/source/_sources.yml`**

```yaml
version: 2

sources:
  - name: harbor
    database: lakehouse
    schema: raw_harbor
    freshness:
      warn_after: {count: 12, period: hour}
      error_after: {count: 24, period: hour}
    loaded_at_field: ingested_at

    tables:
      - name: vessels
        description: "Raw vessel registry from the harbor management system."
        columns:
          - name: vessel_id
            description: "Unique vessel identifier."
          - name: name
            description: "Vessel name."
          - name: vessel_type
            description: "Type of vessel (e.g. sailboat, catamaran, motorboat)."
```

**2. Create the staging model**

Create `models/source/stg_harbor__vessels.sql` — the entire file is one line:

```sql
{{ optimist.stage_source('harbor', 'vessels') }}
```

This generates:

```sql
with source as (

    select * from lakehouse.raw_harbor.vessels

),

staged as (

    select
        vessel_id,
        name,
        vessel_type,
        ...,                                      -- all other columns in the source table
        current_timestamp        as _loaded_at,
        'harbor'                 as _source_name,
        'vessels'                as _source_table

    from source

)

select * from staged
```

**3. Document the staged model in `models/source/_schema.yml`**

```yaml
version: 2

models:
  - name: stg_harbor__vessels
    description: "Staged vessel registry from the harbor source."

    columns:
      - name: vessel_id
        description: "Unique vessel identifier."
        tests:
          - not_null
          - unique

      - name: _loaded_at
        description: "Timestamp of the dbt run that staged this record."
      - name: _source_name
        description: "Logical source name as declared in sources.yml."
      - name: _source_table
        description: "Table name as declared in sources.yml."
```

---

## Macro reference

### `optimist.stage_source`

Generates a complete staging SELECT for a source table. Introspects the live relation
so it always includes all columns, even if `sources.yml` is not fully documented.

```
optimist.stage_source(source_name, table_name, exclude_columns=[])
```

| Argument | Type | Required | Description |
|---|---|---|---|
| `source_name` | string | yes | Source name as declared in `sources.yml` |
| `table_name` | string | yes | Table name as declared in `sources.yml` |
| `exclude_columns` | list | no | Column names to omit (case-insensitive). Audit columns are always excluded automatically. |

**Excluding columns** — useful for PII or columns handled differently downstream:

```sql
{{ optimist.stage_source('harbor', 'crew', exclude_columns=['passport_number', 'date_of_birth']) }}
```

---

### `optimist.add_audit_columns`

Emits the three standard audit columns as a SQL fragment. Used internally by
`stage_source`, but also available for custom models that don't use `stage_source`.

```
optimist.add_audit_columns(source_name, table_name)
```

The snippet must follow a trailing comma from the last business column:

```sql
select
    vessel_id,
    name,
    {{ optimist.add_audit_columns('harbor', 'vessels') }}
from {{ source('harbor', 'vessels') }}
```

**Produced columns:**

| Column | Type | Description |
|---|---|---|
| `_loaded_at` | timestamp | Timestamp of the dbt run |
| `_source_name` | string | Logical source name from `sources.yml` |
| `_source_table` | string | Table name from `sources.yml` |

---

## Config templates

Blank templates are provided in the package and can be copied into your project:

- `models/source/_sources.yml` — source definition template
- `models/source/_schema.yml` — staged model documentation template
