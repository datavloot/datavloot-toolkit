-- One row per hour (UTC) with the Dutch day-ahead price.
-- depends_on: {{ ref('dim_date') }}
-- depends_on: {{ ref('dim_time') }}

{% set fct_source %}
source_cte: hourly_prices
{% endset %}

with

-- imports
prices_raw as (

    select * from {{ ref('stg_energyzero__day_ahead_prices') }}

),

-- transform
hourly_prices as (

    select
        hour_utc,
        hour_local,
        -- the local date and hour: "13:00" means 13:00 in the Netherlands
        {{ optimist.generate_date_key('hour_local') }}  as date_key,
        cast(hour(hour_local) * 3600 as integer)         as time_key,
        price_eur_kwh,
        price_eur_kwh < 0                                as is_negative_price
    from prices_raw

)

{{ optimist.build_fact(fromyaml(fct_source)) }}
