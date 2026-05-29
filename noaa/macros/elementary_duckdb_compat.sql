{# ── DuckDB overrides for Elementary 0.16.x compatibility ─────────────────
   Dispatched via the `dispatch:` config in dbt_project.yml:
     dispatch:
       - macro_namespace: elementary
         search_order: ['noaa', 'elementary']
   ────────────────────────────────────────────────────────────────────── #}

{# DuckDB uses '' not \' to escape single quotes in SQL strings #}
{%- macro duckdb__escape_special_chars(string_value) -%}
    {{- return(string_value | replace("'", "''") | replace("\n", "\\n") | replace("\r", "\\r")) -}}
{%- endmacro -%}

{# Never commit inside a model transaction — DuckDB rejects nested transactions #}
{%- macro duckdb__insert_rows(table_relation, rows, should_commit=false, chunk_size=5000, on_query_exceed=none) -%}
    {{- return(elementary.default__insert_rows(table_relation, rows, false, chunk_size, on_query_exceed)) -}}
{%- endmacro -%}

{# truncate + insert avoids CREATE TABLE conflicts on second run #}
{%- macro duckdb__replace_table_data(relation, rows) -%}
    {%- do dbt.truncate_relation(relation) -%}
    {%- do elementary.insert_rows(relation, rows, should_commit=false, chunk_size=elementary.get_config_var('dbt_artifacts_chunk_size')) -%}
{%- endmacro -%}

{# drop + create_table_as without explicit BEGIN/COMMIT #}
{%- macro duckdb__create_or_replace(temporary, relation, sql_query) -%}
    {%- do dbt.drop_relation_if_exists(relation) -%}
    {%- do elementary.run_query(dbt.create_table_as(temporary, relation, sql_query)) -%}
{%- endmacro -%}

{# DuckDB uses interval multiplication — same syntax as Postgres #}
{%- macro duckdb__edr_timeadd(date_part, number, timestamp_expression) -%}
    {{ elementary.edr_cast_as_timestamp(timestamp_expression) }} + {{ elementary.edr_cast_as_int(number) }} * interval '1 {{ date_part }}'
{%- endmacro -%}
