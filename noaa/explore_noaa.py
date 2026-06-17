import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="NOAA AIS — Guam 2025")


@app.cell
def _():
    import marimo as mo
    import duckdb
    import altair as alt
    from pathlib import Path

    DB_PATH = Path(__file__).parent / "noaa.duckdb"
    con = duckdb.connect(str(DB_PATH), read_only=True)
    mo.md(f"Connected to `{DB_PATH.name}` — {DB_PATH.stat().st_size // 1_000_000} MB")
    return DB_PATH, alt, con, mo


@app.cell
def _(con, mo):
    schemas = con.sql("""
        SELECT table_schema AS schema_name, COUNT(*) AS tables
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        GROUP BY table_schema
        ORDER BY table_schema
    """).df()
    mo.vstack([
        mo.md("## Schemas"),
        mo.ui.table(schemas),
    ])
    return (schemas,)


@app.cell
def _(con, mo):
    total = con.sql("SELECT COUNT(*) AS total_events FROM noaa_business.fct_port_event").fetchone()[0]
    arrivals = con.sql("SELECT COUNT(*) FROM noaa_business.fct_port_event WHERE NOT is_departure").fetchone()[0]
    departures = con.sql("SELECT COUNT(*) FROM noaa_business.fct_port_event WHERE is_departure").fetchone()[0]
    mo.vstack([
        mo.md("## Overview"),
        mo.hstack([
            mo.stat(f"{total:,}", label="Total port events"),
            mo.stat(f"{arrivals:,}", label="Arrivals"),
            mo.stat(f"{departures:,}", label="Departures"),
        ]),
    ])
    return arrivals, departures, total


@app.cell
def _(alt, con, mo):
    monthly = con.sql("""
        SELECT
            STRFTIME(DATE_TRUNC('month', event_time), '%Y-%m') AS month,
            COUNT(*) FILTER (WHERE NOT is_departure) AS arrivals,
            COUNT(*) FILTER (WHERE is_departure)     AS departures
        FROM noaa_business.fct_port_event
        GROUP BY 1
        ORDER BY 1
    """).df()

    chart_monthly = alt.Chart(monthly).transform_fold(
        ['arrivals', 'departures'], as_=['type', 'count']
    ).mark_bar(opacity=0.8).encode(
        x=alt.X('month:O', title='Month'),
        y=alt.Y('count:Q', title='Events'),
        color=alt.Color('type:N', title=''),
        xOffset='type:N',
    ).properties(title='Port events per month', height=300)

    mo.vstack([
        mo.md("## Events per month"),
        mo.ui.altair_chart(chart_monthly),
        mo.ui.table(monthly),
    ])
    return chart_monthly, monthly


@app.cell
def _(alt, con, mo):
    hourly = con.sql("""
        SELECT
            HOUR(event_time) AS hour_of_day,
            COUNT(*) FILTER (WHERE NOT is_departure) AS arrivals,
            COUNT(*) FILTER (WHERE is_departure)     AS departures
        FROM noaa_business.fct_port_event
        GROUP BY 1
        ORDER BY 1
    """).df()

    chart_hourly = alt.Chart(hourly).transform_fold(
        ['arrivals', 'departures'], as_=['type', 'count']
    ).mark_line(point=True).encode(
        x=alt.X('hour_of_day:O', title='Hour of day (UTC)'),
        y=alt.Y('count:Q', title='Events'),
        color=alt.Color('type:N', title=''),
    ).properties(title='Events by hour of day', height=300)

    mo.vstack([
        mo.md("## Events by hour of day"),
        mo.ui.altair_chart(chart_hourly),
        mo.ui.table(hourly),
    ])
    return chart_hourly, hourly


@app.cell
def _(alt, con, mo):
    vessel_types = con.sql("""
        SELECT
            COALESCE(CAST(v.vessel_type AS VARCHAR), 'Unknown') AS vessel_type,
            COUNT(*) AS port_events
        FROM noaa_business.fct_port_event f
        LEFT JOIN noaa_business.dim_vessel v ON f.dim_vessel_key = v.dim_vessel_key
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 15
    """).df()

    chart_vessels = alt.Chart(vessel_types).mark_bar().encode(
        x=alt.X('port_events:Q', title='Port events'),
        y=alt.Y('vessel_type:N', sort='-x', title='Vessel type code'),
    ).properties(title='Top 15 vessel types by port events', height=350)

    mo.vstack([
        mo.md("## Top vessel types"),
        mo.ui.altair_chart(chart_vessels),
        mo.ui.table(vessel_types),
    ])
    return chart_vessels, vessel_types


@app.cell
def _(con, mo):
    sea_states = con.sql("""
        SELECT
            COALESCE(s.label, 'No weather data') AS sea_state,
            COUNT(*) AS port_events,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM noaa_business.fct_port_event f
        LEFT JOIN noaa_business.dim_sea_state s ON f.dim_sea_state_key = s.dim_sea_state_key
        GROUP BY 1
        ORDER BY 2 DESC
    """).df()

    mo.vstack([
        mo.md("## Sea state at time of port event"),
        mo.ui.table(sea_states),
    ])
    return (sea_states,)


if __name__ == "__main__":
    app.run()
