-- Fails if there is sunshine in the middle of the night (23:00-03:00 UTC), which in
-- the Netherlands is dark all year: a sign of shifted timestamps (timezone bug).
select *
from {{ ref('stg_open_meteo__hourly_weather') }}
where hour(hour_utc) in (23, 0, 1, 2)
  and shortwave_radiation_wm2 > 0
