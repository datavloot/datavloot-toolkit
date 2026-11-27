-- Every language in your repositories, with the area of work it stands for
-- (seeds/language_areas.csv); a language the seed does not know is 'Other'.

{%- set dim_source -%}
source_cte: languages
{%- endset %}

with

used as (

    select distinct language from {{ ref('stg_github__repository_languages') }}

),

areas as (

    select * from {{ ref('language_areas') }}

),

languages as (

    select
        used.language,
        coalesce(areas.area, 'Other') as area
    from used
    left join areas using (language)

)

{{ optimist.build_dimension(fromyaml(dim_source)) }}
