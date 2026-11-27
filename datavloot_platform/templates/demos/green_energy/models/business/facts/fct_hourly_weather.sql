-- One row per hour (UTC) per location with wind, sun and temperature.
-- depends_on: {{ ref('dim_location') }}
-- depends_on: {{ ref('dim_date') }}
-- depends_on: {{ ref('dim_time') }}

{% set fct_source %}
source_cte: hourly_weather
{% endset %}

with

-- imports
weather_raw as (

    select * from {{ ref('stg_open_meteo__hourly_weather') }}

),

-- transform
hourly_weather as (

    select
        location_code,
        hour_utc,
        hour_local,
        -- the local date and hour: "13:00" means 13:00 in the Netherlands
        {{ optimist.generate_date_key('hour_local') }}  as date_key,
        cast(hour(hour_local) * 3600 as integer)         as time_key,
        wind_speed_10m_ms,
        shortwave_radiation_wm2,
        temperature_2m_c
    from weather_raw

)

{{ optimist.build_fact(fromyaml(fct_source)) }}
