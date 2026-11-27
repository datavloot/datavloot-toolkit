-- Every local hour belongs to exactly one listening moment, or plays would go
-- missing from the moments (or be counted twice) in fct_play.
with hours as (
    select range as hour from range(0, 24)
)
select hours.hour, count(m.moment_code) as moments
from hours
left join {{ ref('listening_moments') }} m
    on hours.hour >= m.start_hour and hours.hour < m.end_hour
group by hours.hour
having count(m.moment_code) <> 1
