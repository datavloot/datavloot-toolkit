-- Staged day-ahead prices: dlt's own columns dropped, audit columns added by
-- stage_source, and the hour in Dutch local time next to UTC.
with staged as (

    {{ optimist.stage_source('energyzero', 'day_ahead_prices', exclude_columns=['_dlt_load_id', '_dlt_id']) }}

)

select
    timezone('UTC', reading_date)              as hour_utc,
    timezone('Europe/Amsterdam', reading_date) as hour_local,
    price_eur_kwh,
    _loaded_at,
    _source_name,
    _source_table
from staged
