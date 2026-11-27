-- One row per play, in your own time zone (var spotify_timezone in dbt_project.yml):
-- the day, the minute and the listening moment (seeds/listening_moments.csv) are
-- those on your clock, not in UTC.

-- depends_on: {{ ref('dim_track') }}
-- depends_on: {{ ref('dim_artist') }}
-- depends_on: {{ ref('dim_date') }}
-- depends_on: {{ ref('dim_time') }}
-- depends_on: {{ ref('dim_listening_moment') }}

{% set source_config %}
source_cte: plays
{% endset %}

with

plays_raw as (

    select * from {{ ref('stg_spotify__recently_played') }}

),

listening_moments as (

    select * from {{ ref('listening_moments') }}

),

plays_local as (

    select
        played_at,
        timezone('{{ var("spotify_timezone") }}', played_at) as played_at_local,
        track_id,
        artist_id,
        duration_ms,
        context_type
    from plays_raw

),

plays as (

    select
        p.played_at,
        p.played_at_local,
        cast(date_trunc('minute', p.played_at_local) as time) as played_time_minute,
        p.track_id,
        p.artist_id,
        m.moment_code,
        round(p.duration_ms / 60000.0, 2)                       as track_minutes,
        p.context_type
    from plays_local p
    left join listening_moments m
        on  hour(p.played_at_local) >= m.start_hour
        and hour(p.played_at_local) <  m.end_hour

)

{{ optimist.build_fact(fromyaml(source_config)) }}
