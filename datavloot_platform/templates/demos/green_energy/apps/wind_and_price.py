import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Wind, sun and the Dutch power price")


@app.cell
def _():
    # An app: this notebook is in apps/, so the Crows Nest's Dashboards panel runs
    # it with `marimo run`, showing its output and not its code. Explore in
    # notebooks/explore.py; put here what others should read.
    import altair as alt
    import marimo as mo
    import pandas as pd
    from pathlib import Path
    from datavloot_platform import storage

    # Read-only, so the app can stay open while a pipeline writes.
    PROJECT_DIR = Path(__file__).parent.parent
    con = storage.connect(PROJECT_DIR, read_only=True)

    # datavloot's colours, as in the NOAA demo's app: navy for the price, ochre for
    # the weather. They differ in lightness as well as hue, so they stay apart for
    # colour-blind readers.
    PRICE, WIND, NEGATIVE = "#1f3c4e", "#c98a1f", "#b5473a"
    return NEGATIVE, PRICE, WIND, alt, con, mo, pd


@app.cell
def _(con, mo):
    # Before the first pipeline run the lake is empty: say so, rather than let
    # the query below fail with Marimo's bare "An internal error occurred".
    _built = con.sql("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'green_energy_business'
          AND table_name IN ('fct_hourly_price', 'fct_hourly_weather')
    """).fetchone()[0]
    mo.stop(
        _built < 2,
        mo.md(
            "# Wind, sun and the Dutch power price\n"
            "No data yet. In the Crows Nest, open **Pipelines** and click "
            "**Materialize all**; once the run has succeeded, reload this dashboard."
        ),
    )
    lake_built = True
    return (lake_built,)


@app.cell
def _(con, lake_built):
    # One row per hour and location: the price fact joined to the weather fact on
    # the hour, both on the same conformed date and time dimensions. 3 locations x
    # ~17 000 hours: small enough to keep in memory, so every filter is instant.
    assert lake_built
    hours = con.sql("""
        SELECT
            p.hour_utc,
            p.hour_local,
            d.date_day                    AS local_date,
            date_trunc('month', d.date_day) AS local_month,
            t.hour                        AS local_hour,
            p.price_eur_kwh,
            p.is_negative_price,
            l.location_name,
            l.region,
            w.wind_speed_10m_ms,
            w.shortwave_radiation_wm2
        FROM green_energy_business.fct_hourly_price p
        JOIN green_energy_business.dim_date d USING (date_key)
        JOIN green_energy_business.dim_time t USING (time_key)
        JOIN green_energy_business.fct_hourly_weather w USING (hour_utc)
        JOIN green_energy_business.dim_location l USING (location_key)
        ORDER BY p.hour_utc, l.location_name
    """).df()
    months = sorted(hours["local_month"].unique())
    return hours, months


@app.cell
def _(hours, mo, months, pd):
    def month_label(i):
        return pd.Timestamp(months[i]).strftime("%b %Y")

    period = mo.ui.range_slider(
        start=0,
        stop=len(months) - 1,
        value=[0, len(months) - 1],
        label="Period",
        full_width=True,
    )
    location = mo.ui.dropdown(
        options=sorted(hours["location_name"].unique()),
        value="IJmuiden",
        label="Weather at",
    )
    return location, period, month_label


@app.cell
def _(location, mo, period, month_label):
    mo.vstack([
        mo.md(
            "# Wind, sun and the Dutch power price\n"
            "Day-ahead electricity prices (EnergyZero, €/kWh excl. VAT) next to the weather "
            "(Open-Meteo archive) at three places in the Netherlands. Hours of the day are "
            "Dutch local time."
        ),
        mo.hstack(
            [
                mo.vstack([period, mo.md(f"**{month_label(period.value[0])} – {month_label(period.value[1])}**")]),
                location,
            ],
            widths=[3, 1],
            gap=2,
            align="center",
        ),
    ])
    return


@app.cell
def _(hours, location, months, period):
    _first, _last = months[period.value[0]], months[period.value[1]]
    selection = hours[
        hours["local_month"].between(_first, _last)
        & (hours["location_name"] == location.value)
    ]
    return (selection,)


@app.cell
def _(location, mo, selection):
    _negative = int(selection["is_negative_price"].sum())
    _cheapest = selection.loc[selection["price_eur_kwh"].idxmin()]
    mo.hstack(
        [
            mo.stat(f"€{selection['price_eur_kwh'].mean():.3f}", label="Average price per kWh"),
            mo.stat(f"{_negative:,}", label="Hours with a negative price",
                    caption=f"{_negative / len(selection):.1%} of {len(selection):,} hours"),
            mo.stat(f"{selection['wind_speed_10m_ms'].corr(selection['price_eur_kwh']):+.2f}",
                    label="Correlation wind – price", caption=f"wind at {location.value}"),
            mo.stat(f"{selection['shortwave_radiation_wm2'].corr(selection['price_eur_kwh']):+.2f}",
                    label="Correlation sun – price", caption=f"sun at {location.value}"),
            mo.stat(f"{'−' if _cheapest['price_eur_kwh'] < 0 else ''}€{abs(_cheapest['price_eur_kwh']):.3f}",
                    label="Cheapest hour",
                    caption=_cheapest["hour_local"].strftime("%d %b %Y, %H:00")),
        ],
        widths="equal",
        gap=1,
    )
    return


@app.cell
def _(PRICE, WIND, alt, location, mo, selection):
    _daily = (
        selection.groupby("local_date")
        .agg(price=("price_eur_kwh", "mean"), wind=("wind_speed_10m_ms", "mean"))
        .reset_index()
    )
    _base = alt.Chart(_daily).encode(x=alt.X("local_date:T", title=None))
    _price = _base.mark_line(color=PRICE, strokeWidth=1.4).encode(
        y=alt.Y("price:Q", title="Price, €/kWh (daily average)", axis=alt.Axis(titleColor=PRICE)),
        tooltip=[alt.Tooltip("local_date:T", title="Day"), alt.Tooltip("price:Q", title="€/kWh", format=".3f"),
                 alt.Tooltip("wind:Q", title="Wind, m/s", format=".1f")],
    )
    _wind = _base.mark_line(color=WIND, strokeWidth=1.2, opacity=0.85).encode(
        y=alt.Y("wind:Q", title=f"Wind at {location.value}, m/s", axis=alt.Axis(titleColor=WIND)),
    )
    _chart = alt.layer(_price, _wind).resolve_scale(y="independent").properties(width="container", height=260)
    mo.vstack([mo.md("## Price and wind over time"), _chart])
    return


@app.cell
def _(PRICE, WIND, alt, location, mo, selection):
    _points = (
        alt.Chart(selection[["wind_speed_10m_ms", "price_eur_kwh"]])
        .mark_circle(size=9, opacity=0.18, color=PRICE)
        .encode(
            x=alt.X("wind_speed_10m_ms:Q", title=f"Wind speed at {location.value}, m/s"),
            y=alt.Y("price_eur_kwh:Q", title="Price, €/kWh"),
        )
    )
    # The average price per 1 m/s of wind, on top of the cloud of hours
    _bands = (
        selection.assign(wind=selection["wind_speed_10m_ms"].round())
        .groupby("wind")
        .agg(price=("price_eur_kwh", "mean"), n=("price_eur_kwh", "size"))
        .reset_index()
    )
    _mean = (
        alt.Chart(_bands[_bands["n"] >= 20])
        .mark_line(color=WIND, strokeWidth=3, point=True)
        .encode(
            x="wind:Q",
            y="price:Q",
            tooltip=[alt.Tooltip("wind:Q", title="Wind, m/s"), alt.Tooltip("price:Q", title="Average €/kWh", format=".3f"),
                     alt.Tooltip("n:Q", title="Hours", format=",")],
        )
    )
    _chart = alt.layer(_points, _mean).properties(width="container", height=300)
    mo.vstack([
        mo.md("## Wind speed vs price\nEach dot is one hour; the line is the average price per m/s of wind."),
        _chart,
    ])
    return


@app.cell
def _(NEGATIVE, PRICE, alt, mo, selection):
    _by_hour = (
        selection.groupby("local_hour")
        .agg(price=("price_eur_kwh", "mean"), negative=("is_negative_price", "sum"))
        .reset_index()
    )
    _chart = (
        alt.Chart(_by_hour)
        .mark_bar(color=PRICE)
        .encode(
            x=alt.X("local_hour:O", title="Hour of the day (Europe/Amsterdam)", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("price:Q", title="Average price, €/kWh"),
            color=alt.condition(alt.datum.price < 0, alt.value(NEGATIVE), alt.value(PRICE)),
            tooltip=[alt.Tooltip("local_hour:O", title="Hour"), alt.Tooltip("price:Q", title="Average €/kWh", format=".3f"),
                     alt.Tooltip("negative:Q", title="Negative hours")],
        )
        .properties(width="container", height=260)
    )
    mo.vstack([mo.md("## Average price by hour of the day"), _chart])
    return


@app.cell
def _(NEGATIVE, alt, mo, selection):
    _monthly = (
        selection.groupby("local_month")
        .agg(negative=("is_negative_price", "sum"), lowest=("price_eur_kwh", "min"))
        .reset_index()
    )
    _chart = (
        alt.Chart(_monthly)
        .mark_bar(color=NEGATIVE)
        .encode(
            x=alt.X("yearmonth(local_month):O", title=None),
            y=alt.Y("negative:Q", title="Hours with a negative price"),
            tooltip=[alt.Tooltip("yearmonth(local_month):O", title="Month"),
                     alt.Tooltip("negative:Q", title="Negative hours"),
                     alt.Tooltip("lowest:Q", title="Lowest €/kWh", format=".3f")],
        )
        .properties(width="container", height=260)
    )
    _lowest = (
        selection.nsmallest(10, "price_eur_kwh")
        .assign(
            hour=lambda t: t["hour_local"].dt.strftime("%a %d %b %Y, %H:00"),
            price=lambda t: t["price_eur_kwh"].round(3),
            wind=lambda t: t["wind_speed_10m_ms"].round(1),
            sun=lambda t: t["shortwave_radiation_wm2"].round(),
        )[["hour", "price", "wind", "sun"]]
        .rename(columns={"hour": "Hour (local)", "price": "€/kWh", "wind": "Wind, m/s", "sun": "Sun, W/m²"})
        .reset_index(drop=True)
    )
    mo.hstack(
        [
            mo.vstack([mo.md("## Negative-price hours per month"), _chart]),
            mo.vstack([
                mo.md("## The ten cheapest hours"),
                mo.ui.table(_lowest, selection=None, show_column_summaries=False, show_data_types=False, pagination=False),
            ]),
        ],
        widths="equal",
        gap=2,
        align="start",
    )
    return


if __name__ == "__main__":
    app.run()
