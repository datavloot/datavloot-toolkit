-- Every day between the first and the last calendar day has a row: the calendar
-- query covers whole years, so a gap means a failed load.
with days as (
    select d.date_day
    from {{ ref('fct_contribution_day') }} f
    join {{ ref('dim_date') }} d on f.contribution_date_key = d.date_key
),

expected as (
    select unnest(generate_series(min(date_day), max(date_day), interval 1 day))::date as date_day
    from days
)

select expected.date_day
from expected
left join days using (date_day)
where days.date_day is null
