-- Staged hourly weather per location: dlt's own columns dropped, audit columns
-- added by stage_source, and the hour in Dutch local time next to UTC.
with staged as (

    {{ optimist.stage_source('open_meteo', 'hourly_weather', exclude_columns=['_dlt_load_id', '_dlt_id']) }}

)

select
    location_code,
    timezone('UTC', observed_at)              as hour_utc,
    timezone('Europe/Amsterdam', observed_at) as hour_local,
    wind_speed_10m_ms,
    shortwave_radiation_wm2,
    temperature_2m_c,
    _loaded_at,
    _source_name,
    _source_table
from staged
