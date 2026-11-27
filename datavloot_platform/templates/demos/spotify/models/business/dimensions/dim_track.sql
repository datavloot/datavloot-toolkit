-- Every track that shows up anywhere: played, liked, in a top list or on a playlist.
-- One row per track, from the most recent place it was seen; is_saved and saved_at
-- say whether it is in your Liked Songs.

{%- set dim_source -%}
source_cte: tracks
{%- endset %}

with

plays as (

    select * from {{ ref('stg_spotify__recently_played') }}

),

saved as (

    select * from {{ ref('stg_spotify__saved_tracks') }}

),

top as (

    select * from {{ ref('stg_spotify__top_tracks') }}

),

playlist_items as (

    select * from {{ ref('stg_spotify__playlist_items') }}

),

seen as (

    select track_id, track_name, duration_ms, is_explicit, album_id, album_name, album_release_date,
           artist_id, artist_name, artist_names, played_at as seen_at
    from plays
    union all
    select track_id, track_name, duration_ms, is_explicit, album_id, album_name, album_release_date,
           artist_id, artist_name, artist_names, added_at
    from saved
    union all
    select track_id, track_name, duration_ms, is_explicit, album_id, album_name, album_release_date,
           artist_id, artist_name, artist_names, cast(snapshot_date as timestamptz)
    from top
    union all
    select track_id, track_name, duration_ms, is_explicit, album_id, album_name, album_release_date,
           artist_id, artist_name, artist_names, added_at
    from playlist_items

),

tracks as (

    select
        seen.*,
        saved.track_id is not null as is_saved,
        saved.added_at             as saved_at
    from seen
    left join saved using (track_id)

)

{{ optimist.build_dimension(fromyaml(dim_source)) }}
