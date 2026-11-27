-- One row per commit, in your own time zone (var github_timezone in dbt_project.yml):
-- the day and the minute are those on your clock, not in UTC.

-- depends_on: {{ ref('dim_repository') }}
-- depends_on: {{ ref('dim_date') }}
-- depends_on: {{ ref('dim_time') }}

{% set source_config %}
source_cte: commits
{% endset %}

with

commits_raw as (

    select * from {{ ref('stg_github__commits') }}

),

commits as (

    select
        sha,
        repository_id,
        authored_at,
        timezone('{{ var("github_timezone") }}', authored_at)                                    as authored_at_local,
        cast(date_trunc('minute', timezone('{{ var("github_timezone") }}', authored_at)) as time) as authored_time_minute,
        message_title
    from commits_raw

)

{{ optimist.build_fact(fromyaml(source_config)) }}
