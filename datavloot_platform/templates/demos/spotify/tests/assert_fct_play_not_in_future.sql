-- A play can only be in the past. A play in the future means a time zone went
-- wrong somewhere between Spotify (UTC) and fct_play.
select *
from {{ ref('fct_play') }}
where played_at > now() + interval 5 minute
