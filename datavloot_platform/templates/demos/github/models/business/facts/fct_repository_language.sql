-- How much code each repository has in each language. Grain: repository x language.

-- depends_on: {{ ref('dim_repository') }}
-- depends_on: {{ ref('dim_language') }}

{% set source_config %}
source_cte: sizes
{% endset %}

with

sizes_raw as (

    select * from {{ ref('stg_github__repository_languages') }}

),

sizes as (

    select
        repository_id,
        language,
        bytes,
        round(bytes / sum(bytes) over (partition by repository_id), 4) as share_of_repository
    from sizes_raw

)

{{ optimist.build_fact(fromyaml(source_config)) }}
