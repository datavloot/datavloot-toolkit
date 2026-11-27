-- Every artist that shows up: as a track's main artist, in your top artists or
-- among the artists you follow. Genres come from the last two; for an artist
-- seen only on a track they are empty.

{%- set dim_source -%}
source_cte: artists
{%- endset %}

with

tracks as (

    select * from {{ ref('dim_track') }}

),

top as (

    select * from {{ ref('stg_spotify__top_artists') }}

),

followed as (

    select * from {{ ref('stg_spotify__followed_artists') }}

),

seen as (

    select artist_id, artist_name, null as genres from tracks where artist_id is not null
    union all
    select artist_id, artist_name, genres from top
    union all
    select artist_id, artist_name, genres from followed

),

artists as (

    select
        seen.*,
        followed.artist_id is not null as is_followed
    from seen
    left join followed using (artist_id)

)

{{ optimist.build_dimension(fromyaml(dim_source)) }}
