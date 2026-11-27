import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full", app_title="Listening habits")


@app.cell
def _():
    # An app: this notebook is in apps/, so the Crows Nest's Dashboards tab runs
    # it with `marimo run`, showing its output and not its code. Explore in
    # notebooks/explore_spotify.py; put here what others should read.
    import altair as alt
    import marimo as mo
    import pandas as pd
    from pathlib import Path
    from datavloot_platform import storage

    # Read-only, so the app can stay open while a pipeline writes.
    PROJECT_DIR = Path(__file__).parent.parent
    con = storage.connect(PROJECT_DIR, read_only=True)

    # The colours of branding/branding.yml: a music app's green and near-black,
    # which differ in lightness as well as hue, so they stay apart for
    # colour-blind readers; a ramp from pale green to black for the heatmap.
    INK, GREEN = "#191414", "#1db954"
    RAMP = ["#e8f8ee", "#a6e8bf", "#1ed760", "#168d40", "#191414"]
    return INK, GREEN, RAMP, alt, con, mo, pd


@app.cell
def _(con, mo):
    # Before the first pipeline run the lake is empty: say so, rather than let
    # the query below fail with Marimo's bare "An internal error occurred".
    _built = con.sql("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'spotify_business' AND table_name = 'fct_play'
    """).fetchone()[0]
    mo.stop(
        not _built,
        mo.md(
            "# Listening habits\n"
            "No data yet. In the Crows Nest, open **Pipelines** and click "
            "**Materialize all**; once the run has succeeded, reload this dashboard."
        ),
    )
    lake_built = True
    return (lake_built,)


@app.cell
def _(con, lake_built):
    assert lake_built
    # Whose data this is: the sample, or the connected account.
    origin, listener = con.sql("""
        SELECT origin, coalesce(display_name, user_id) FROM source.account LIMIT 1
    """).fetchone()
    plays = con.sql("""
        SELECT
            f.played_at_local,
            t.track_name,
            a.artist_name,
            coalesce(a.genres, '') AS genres,
            m.label AS moment,
            m.start_hour AS moment_order,
            f.track_minutes,
            coalesce(f.context_type, 'unknown') AS context_type
        FROM spotify_business.fct_play f
        JOIN spotify_business.dim_track t USING (track_key)
        LEFT JOIN spotify_business.dim_artist a USING (artist_key)
        JOIN spotify_business.dim_listening_moment m USING (listening_moment_key)
    """).df()
    return listener, origin, plays


@app.cell
def _(listener, mo, origin, plays):
    _first = plays["played_at_local"].min()
    _last = plays["played_at_local"].max()
    _days = max(1, (_last - _first).days + 1) if len(plays) else 1
    days = mo.ui.slider(start=1, stop=_days, value=_days, label="Last days", show_value=True)
    _note = (
        "**Sample data**: made-up listening history. Connect your own account with "
        "`uv run python -m spotify_platform.connect` (README)."
        if origin == "sample"
        else f"Plays of **{listener}**, collected since {_first:%d %B %Y}. Spotify keeps only the "
             "last 50, so the history grows with every run."
    )
    mo.vstack([mo.md(f"# Listening habits\n{_note}"), days])
    return (days,)


@app.cell
def _(days, pd, plays):
    _since = plays["played_at_local"].max() - pd.to_timedelta(int(days.value), unit="D")
    selection = plays[plays["played_at_local"] > _since]
    return (selection,)


@app.cell
def _(mo, selection):
    _hours = selection["track_minutes"].sum() / 60
    _by_hour = selection["played_at_local"].dt.hour.value_counts()
    mo.hstack(
        [
            mo.stat(f"{len(selection):,}", label="Plays"),
            mo.stat(f"{_hours:,.0f} h", label="Listening time (track length)"),
            mo.stat(f"{selection['artist_name'].nunique():,}", label="Artists"),
            mo.stat(f"{_by_hour.idxmax():02d}:00" if len(_by_hour) else "–", label="Busiest hour"),
        ],
        widths="equal",
        gap=1,
    )
    return


@app.cell
def _(RAMP, alt, mo, selection):
    _grid = (
        selection.assign(
            weekday=selection["played_at_local"].dt.day_name(),
            hour=selection["played_at_local"].dt.hour,
        )
        .groupby(["weekday", "hour"])
        .size()
        .reset_index(name="plays")
    )
    _days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    _chart = (
        alt.Chart(_grid)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("hour:O", title="Hour of day (your time)", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("weekday:N", title=None, sort=_days),
            color=alt.Color("plays:Q", title="Plays", scale=alt.Scale(range=RAMP)),
            tooltip=[
                alt.Tooltip("weekday:N", title="Day"),
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("plays:Q", title="Plays"),
            ],
        )
        .properties(width="container", height=220)
    )
    mo.vstack([mo.md("## When you listen"), _chart])
    return


@app.cell
def _(INK, GREEN, alt, mo, selection):
    def _bars(counts, field, title, color):
        return (
            alt.Chart(counts)
            .mark_bar(color=color, cornerRadiusEnd=3, size=16)
            .encode(
                x=alt.X("plays:Q", title="Plays"),
                y=alt.Y(f"{field}:N", title=None, sort="-x", axis=alt.Axis(labelLimit=220)),
                tooltip=[alt.Tooltip(f"{field}:N", title=title), alt.Tooltip("plays:Q", title="Plays", format=",")],
            )
            .properties(width="container", height=alt.Step(26))
        )

    _artists = selection.groupby("artist_name").size().reset_index(name="plays").nlargest(10, "plays")
    _tracks = (
        selection.assign(track=selection["track_name"] + " — " + selection["artist_name"])
        .groupby("track").size().reset_index(name="plays").nlargest(10, "plays")
    )
    mo.hstack(
        [
            mo.vstack([mo.md("## Most played artists"), _bars(_artists, "artist_name", "Artist", INK)]),
            mo.vstack([mo.md("## Most played tracks"), _bars(_tracks, "track", "Track", GREEN)]),
        ],
        widths="equal",
        gap=2,
        align="start",
    )
    return


@app.cell
def _(INK, alt, mo, selection):
    _moments = (
        selection.groupby(["moment", "moment_order"]).size().reset_index(name="plays")
        .sort_values("moment_order")
    )
    _chart = (
        alt.Chart(_moments)
        .mark_bar(color=INK, cornerRadiusEnd=3, size=18)
        .encode(
            x=alt.X("plays:Q", title="Plays"),
            y=alt.Y("moment:N", title=None, sort=list(_moments["moment"])),
            tooltip=[alt.Tooltip("moment:N", title="Moment"), alt.Tooltip("plays:Q", title="Plays", format=",")],
        )
        .properties(width="container", height=alt.Step(28))
    )
    _top_by_moment = (
        selection.groupby(["moment_order", "moment", "artist_name"]).size().reset_index(name="plays")
        .sort_values(["moment_order", "plays"], ascending=[True, False])
        .groupby("moment").head(1)
        .rename(columns={"moment": "Moment", "artist_name": "Favourite artist", "plays": "Plays"})
        [["Moment", "Favourite artist", "Plays"]]
        .reset_index(drop=True)
    )
    mo.hstack(
        [
            mo.vstack([mo.md("## By moment of the day"), _chart]),
            mo.vstack([
                mo.md("## Your soundtrack per moment"),
                mo.ui.table(_top_by_moment, selection=None, show_column_summaries=False,
                            show_data_types=False, pagination=False),
            ]),
        ],
        widths="equal",
        gap=2,
        align="start",
    )
    return


if __name__ == "__main__":
    app.run()
