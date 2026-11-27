{%- set dim_source -%}
source_seed: locations
{%- endset -%}

{{ optimist.build_dimension(fromyaml(dim_source)) }}
