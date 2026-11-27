-- One row per day of the contribution calendar, the green squares on a GitHub
-- profile: commits, pull requests, reviews and issues, private work included.

-- depends_on: {{ ref('dim_date') }}

{% set source_config %}
source_cte: days
{% endset %}

with

days_raw as (

    select * from {{ ref('stg_github__contribution_days') }}

),

days as (

    select
        contribution_date,
        contributions,
        contributions > 0 as is_active
    from days_raw

)

{{ optimist.build_fact(fromyaml(source_config)) }}
