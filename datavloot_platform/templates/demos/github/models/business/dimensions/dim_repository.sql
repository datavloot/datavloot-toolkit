{%- set dim_source -%}
source_model: stg_github__repositories
{%- endset -%}

{{ optimist.build_dimension(fromyaml(dim_source)) }}
