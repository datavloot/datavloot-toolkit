{%- set dim_source -%}
source_model: stg_spotify__playlists
{%- endset -%}

{{ optimist.build_dimension(fromyaml(dim_source)) }}
