-- Arrival/departure events derived from AIS position broadcasts.
--
-- Detection logic:
--   1. Parse lon/lat out of the geometry string (WKT POINT format).
--   2. Restrict to ports near Guam (lat 12–15, lon 143–146) to keep the
--      cross-join small before computing full Haversine distances.
--   3. For each (vessel, port) pair ordered by time, flag broadcasts within
--      1.5 nautical miles of the port as "at port".
--   4. A state change from NOT-at-port → at-port = arrival.
--      A state change from at-port → NOT-at-port = departure.

with broadcasts as (

    select
        mmsi,
        base_date_time,
        sog,
        status,
        -- Extract longitude and latitude from "POINT (lon lat)" WKT string
        cast(regexp_extract(geometry, 'POINT \(([0-9.\-]+) [0-9.\-]+\)', 1) as double) as longitude,
        cast(regexp_extract(geometry, 'POINT \([0-9.\-]+ ([0-9.\-]+)\)', 1) as double) as latitude
    from {{ ref('stg_noaa__guam_2025') }}

),

guam_ports as (

    -- Only ports near Guam; reduces the cross-join before the distance calc
    select
        port_index_number,
        latitude  as port_lat,
        longitude as port_lon
    from {{ ref('ports') }}
    where latitude  between 12.0 and 15.0
      and longitude between 143.0 and 146.0

),

proximity as (

    select
        b.mmsi,
        b.base_date_time,
        b.sog,
        b.status,
        p.port_index_number,
        -- Haversine distance in nautical miles (1 NM = 1852 m; Earth radius = 6371 km)
        2 * 3440.065 * asin(sqrt(
            power(sin(radians((p.port_lat - b.latitude)  / 2)), 2) +
            cos(radians(b.latitude)) * cos(radians(p.port_lat)) *
            power(sin(radians((p.port_lon - b.longitude) / 2)), 2)
        )) as distance_nm
    from broadcasts b
    cross join guam_ports p
    where b.latitude  is not null
      and b.longitude is not null

),

classified as (

    select
        mmsi,
        base_date_time,
        sog,
        status,
        port_index_number,
        distance_nm <= 1.5 as is_at_port
    from proximity

),

transitions as (

    select
        mmsi,
        base_date_time,
        sog,
        status,
        port_index_number,
        is_at_port,
        coalesce(
            lag(is_at_port) over (
                partition by mmsi, port_index_number
                order by base_date_time
            ),
            false   -- treat the very first broadcast as "was not at port"
        ) as prev_is_at_port
    from classified

),

port_events as (

    select
        mmsi,
        base_date_time                              as event_time,
        -- Truncate to minute for dim_time join (dim_time has no seconds)
        cast(date_trunc('minute', base_date_time) as time) as event_time_minute,
        port_index_number,
        sog,
        status,
        -- departure = was at port, now leaving; arrival = was outside, now inside
        (prev_is_at_port = true and is_at_port = false) as is_departure
    from transitions
    where
        -- arrival: was outside port zone, now inside
        (prev_is_at_port = false and is_at_port = true)
        -- departure: was inside port zone, now outside
        or (prev_is_at_port = true  and is_at_port = false)

)

{{ optimist.build_fact() }}
