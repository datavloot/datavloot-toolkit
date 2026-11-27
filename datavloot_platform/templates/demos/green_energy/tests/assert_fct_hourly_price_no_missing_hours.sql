-- Fails for every hour between the first and the last price that has no price.
-- The day-ahead market sets a price for every hour, so a gap means a failed load.
with

prices as (

    select hour_utc from {{ ref('fct_hourly_price') }}

),

hours as (

    select unnest(generate_series(min(hour_utc), max(hour_utc), interval 1 hour)) as hour_utc
    from prices

)

select hours.hour_utc
from hours
left join prices using (hour_utc)
where prices.hour_utc is null
