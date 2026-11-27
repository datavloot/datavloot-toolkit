{#
    A GitHub table as stage_source stages it, keeping only the rows of the data
    the project is on now: the sample until an account is connected, the
    account's own from then on.

    `profile` holds one row, replaced on every run, whose `origin` says which
    (sample or github). `commits` keeps history and so still holds the sample's
    rows after an account is connected; this leaves them out without deleting
    anything.
#}
{%- macro stage_github(table_name) -%}
with staged as (

    {{ optimist.stage_source('github', table_name, exclude_columns=['_dlt_load_id', '_dlt_id']) }}

)

select * exclude (origin)
from staged
where origin = (select origin from {{ source('github', 'profile') }})
{%- endmacro -%}
