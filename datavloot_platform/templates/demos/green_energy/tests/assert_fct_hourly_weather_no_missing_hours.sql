-- Fails for every location and hour, between the first and the last observation,
-- that has no weather row: each hour must have one row per location.
-- (Only refs the fact itself, so Elementary files the test under it.)
with

weather as (

    select location_key, hour_utc from {{ ref('fct_hourly_weather') }}

),

locations as (

    select distinct location_key from weather

),

hours as (

    select unnest(generate_series(min(hour_utc), max(hour_utc), interval 1 hour)) as hour_utc
    from weather

)

select locations.location_key, hours.hour_utc
from hours
cross join locations
left join weather using (location_key, hour_utc)
where weather.hour_utc is null
