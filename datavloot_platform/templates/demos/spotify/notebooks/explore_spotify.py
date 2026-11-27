import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Spotify — explore")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    from datavloot_platform import storage

    # Read-only, so the notebook can stay open while a pipeline writes. On
    # DuckDB's default connection, so SQL cells find the lake on either engine
    # Marimo offers: "con" or its own "DuckDB (in-memory)".
    PROJECT_DIR = Path(__file__).parent.parent
    con = storage.connect(PROJECT_DIR, read_only=True, default=True)
    mo.md(f"Connected to the lake in `{storage.lake_dir(PROJECT_DIR)}`")
    return con, mo


@app.cell
def _(con, mo):
    # current_database(): the lake, not DuckLake's own metadata tables
    schemas = con.sql("""
        SELECT table_schema AS schema_name, COUNT(*) AS tables
        FROM information_schema.tables
        WHERE table_catalog = current_database()
        GROUP BY table_schema
        ORDER BY table_schema
    """).df()
    account = con.sql("SELECT * FROM source.account").df()
    mo.vstack([
        mo.md("## Schemas"),
        mo.ui.table(schemas),
        mo.md("## Whose data\n`origin` is *sample* until you connect your own account."),
        mo.ui.table(account),
    ])
    return


@app.cell
def _(con, mo):
    per_day = con.sql("""
        SELECT d.date_day, d.day_name, COUNT(*) AS plays, ROUND(SUM(f.track_minutes) / 60, 1) AS hours
        FROM spotify_business.fct_play f
        JOIN spotify_business.dim_date d ON f.played_date_key = d.date_key
        GROUP BY ALL
        ORDER BY d.date_day DESC
    """).df()
    mo.vstack([mo.md("## Plays per day"), mo.ui.table(per_day)])
    return


@app.cell
def _(con, mo):
    # The rankings Spotify keeps itself, next to what you actually played here.
    rankings = con.sql("""
        WITH latest AS (SELECT max(snapshot_date) AS day FROM source.top_artists)
        SELECT t.time_range, t.rank, t.artist_name, t.genres
        FROM source.top_artists t, latest
        WHERE t.snapshot_date = latest.day AND t.rank <= 10
          AND t.origin = (SELECT origin FROM source.account)
        ORDER BY t.time_range, t.rank
    """).df()
    mo.vstack([
        mo.md("## Spotify's own top 10 artists\nPer time range: *short_term* is about four weeks, "
              "*medium_term* six months, *long_term* a year."),
        mo.ui.table(rankings),
    ])
    return


@app.cell
def _(con, mo):
    # Liked, but how often played? Tracks in Liked Songs never played since you connected.
    forgotten = con.sql("""
        SELECT t.track_name, t.artist_name, t.saved_at
        FROM spotify_business.dim_track t
        LEFT JOIN spotify_business.fct_play f USING (track_key)
        WHERE t.is_saved
        GROUP BY ALL
        HAVING COUNT(f.fct_play_key) = 0
        ORDER BY t.saved_at
    """).df()
    mo.vstack([mo.md("## Liked, but not played"), mo.ui.table(forgotten)])
    return


if __name__ == "__main__":
    app.run()
