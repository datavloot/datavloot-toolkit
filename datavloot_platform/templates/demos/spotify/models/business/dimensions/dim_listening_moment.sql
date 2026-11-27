{%- set dim_source -%}
source_seed: listening_moments
{%- endset -%}

{{ optimist.build_dimension(fromyaml(dim_source)) }}
