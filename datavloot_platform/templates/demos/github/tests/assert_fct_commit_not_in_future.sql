-- A commit can only be in the past. One in the future means a time zone went
-- wrong somewhere between GitHub (UTC) and fct_commit.
select *
from {{ ref('fct_commit') }}
where authored_at > now() + interval 5 minute
