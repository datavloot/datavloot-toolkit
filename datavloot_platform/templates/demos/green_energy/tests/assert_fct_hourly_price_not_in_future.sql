-- Fails if a price lies after the current hour. We load closed days only, so even
-- tomorrow's day-ahead prices (already published) should not be here.
select *
from {{ ref('fct_hourly_price') }}
where hour_utc > timezone('UTC', current_timestamp)
