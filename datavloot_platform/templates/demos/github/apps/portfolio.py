import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full", app_title="Developer portfolio")


@app.cell
def _():
    # An app: this notebook is in apps/, so the Crows Nest's Dashboards tab runs
    # it with `marimo run`, showing its output and not its code. Explore in
    # notebooks/explore_github.py; put here what others should read.
    import altair as alt
    import marimo as mo
    import pandas as pd
    from pathlib import Path
    from datavloot_platform import storage

    # Read-only, so the app can stay open while a pipeline writes.
    PROJECT_DIR = Path(__file__).parent.parent
    con = storage.connect(PROJECT_DIR, read_only=True)

    # The colours of branding/branding.yml: a contribution graph's greens, from
    # an empty day to a busy one, and a code host's blue and dark grey.
    GREENS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    BLUE, INK = "#0969da", "#24292f"
    return BLUE, GREENS, INK, alt, con, mo, pd


@app.cell
def _(con, mo):
    # Before the first pipeline run the lake is empty: say so, rather than let
    # the query below fail with Marimo's bare "An internal error occurred".
    _built = con.sql("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'github_business' AND table_name = 'fct_commit'
    """).fetchone()[0]
    mo.stop(
        not _built,
        mo.md(
            "# Developer portfolio\n"
            "No data yet. In the Crows Nest, open **Pipelines** and click "
            "**Materialize all**; once the run has succeeded, reload this dashboard."
        ),
    )
    lake_built = True
    return (lake_built,)


@app.cell
def _(con, lake_built):
    assert lake_built
    profile = con.sql("SELECT * FROM source.profile LIMIT 1").df().iloc[0]
    days = con.sql("""
        SELECT d.date_day, f.contributions
        FROM github_business.fct_contribution_day f
        JOIN github_business.dim_date d ON f.contribution_date_key = d.date_key
        ORDER BY d.date_day
    """).df()
    commits = con.sql("""
        SELECT f.authored_at_local, r.repository_name, r.is_private
        FROM github_business.fct_commit f
        LEFT JOIN github_business.dim_repository r USING (repository_key)
    """).df()
    languages = con.sql("""
        SELECT l.language, l.area, sum(f.bytes) AS bytes
        FROM github_business.fct_repository_language f
        JOIN github_business.dim_language l USING (language_key)
        GROUP BY ALL
    """).df()
    repositories = con.sql("""
        SELECT r.repository_name, r.description, r.primary_language, r.stars, r.is_private, r.is_fork,
               r.pushed_at, count(f.fct_commit_key) AS commits
        FROM github_business.dim_repository r
        LEFT JOIN github_business.fct_commit f USING (repository_key)
        GROUP BY ALL
    """).df()
    return commits, days, languages, profile, repositories


@app.cell
def _(mo, profile):
    show_private = mo.ui.switch(value=False, label="Include private repositories")
    _who = profile["name"] or profile["login"]
    _note = (
        "**Sample data**: a made-up developer. Connect your own account with "
        "`uv run python -m github_platform.connect` (README)."
        if profile["origin"] == "sample"
        else f"github.com/{profile['login']}"
    )
    _bio = f"\n\n{profile['bio']}" if profile["bio"] else ""
    mo.vstack([mo.md(f"# {_who}\n{_note}{_bio}"), show_private])
    return (show_private,)


@app.cell
def _(commits, pd, repositories, show_private):
    # Private repositories stay out unless switched on: this page is meant to be shown.
    shown_commits = commits if show_private.value else commits[~commits["is_private"].fillna(False).astype(bool)]
    shown_repos = repositories if show_private.value else repositories[~repositories["is_private"].astype(bool)]
    year_ago = pd.Timestamp.now().normalize() - pd.to_timedelta(364, unit="D")
    return shown_commits, shown_repos, year_ago


@app.cell
def _(days, mo, pd, shown_commits, shown_repos, year_ago):
    _year = days[pd.to_datetime(days["date_day"]) >= year_ago]
    _active = (_year["contributions"] > 0).astype(int)
    # The longest run of active days in the last year.
    _streak = int(_active.groupby((_active != _active.shift()).cumsum()).sum().max() or 0)
    mo.hstack(
        [
            mo.stat(f"{int(_year['contributions'].sum()):,}", label="Contributions, last 12 months"),
            mo.stat(f"{int(_active.sum())}", label="Active days, last 12 months"),
            mo.stat(f"{_streak} days", label="Longest streak"),
            mo.stat(f"{len(shown_commits):,}", label="Commits in own repositories"),
            mo.stat(f"{len(shown_repos[~shown_repos['is_fork'].astype(bool)])}", label="Repositories"),
        ],
        widths="equal",
        gap=1,
    )
    return


@app.cell
def _(GREENS, alt, days, mo, pd, year_ago):
    # The calendar as on a profile page: a column per week, a row per weekday.
    _cal = days.assign(date_day=pd.to_datetime(days["date_day"]))
    _cal = _cal[_cal["date_day"] >= year_ago - pd.to_timedelta(int(year_ago.weekday()), unit="D")].copy()
    _cal["week"] = (_cal["date_day"] - _cal["date_day"].min()).dt.days // 7
    _cal["weekday"] = _cal["date_day"].dt.day_name().str[:3]
    _max = max(1, int(_cal["contributions"].quantile(0.95)))
    _cal["level"] = pd.cut(_cal["contributions"], bins=[-1, 0, _max * 0.25, _max * 0.5, _max * 0.75, 10**9],
                           labels=[0, 1, 2, 3, 4]).astype(int)
    _chart = (
        alt.Chart(_cal)
        .mark_rect(cornerRadius=2, stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("week:O", title=None, axis=None),
            y=alt.Y("weekday:N", title=None, sort=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
            color=alt.Color("level:O", scale=alt.Scale(domain=[0, 1, 2, 3, 4], range=GREENS), legend=None),
            tooltip=[alt.Tooltip("date_day:T", title="Day", format="%a %d %b %Y"),
                     alt.Tooltip("contributions:Q", title="Contributions")],
        )
        .properties(width="container", height=150)
    )
    mo.vstack([mo.md("## Contributions in the last year"), _chart])
    return


@app.cell
def _(BLUE, alt, languages, mo):
    _areas = languages.groupby("area", as_index=False)["bytes"].sum()
    _areas["share"] = _areas["bytes"] / _areas["bytes"].sum()
    _top = languages.nlargest(10, "bytes").assign(share=lambda t: t["bytes"] / languages["bytes"].sum())

    def _bars(frame, field, title):
        return (
            alt.Chart(frame)
            .mark_bar(color=BLUE, cornerRadiusEnd=3, size=16)
            .encode(
                x=alt.X("share:Q", title="Share of code", axis=alt.Axis(format="%")),
                y=alt.Y(f"{field}:N", title=None, sort="-x"),
                tooltip=[alt.Tooltip(f"{field}:N", title=title), alt.Tooltip("share:Q", format=".1%")],
            )
            .properties(width="container", height=alt.Step(26))
        )

    mo.hstack(
        [
            mo.vstack([mo.md("## What kind of work"), _bars(_areas, "area", "Area")]),
            mo.vstack([mo.md("## Languages"), _bars(_top, "language", "Language")]),
        ],
        widths="equal", gap=2, align="start",
    )
    return


@app.cell
def _(GREENS, alt, mo, shown_commits):
    _grid = (
        shown_commits.assign(
            weekday=shown_commits["authored_at_local"].dt.day_name(),
            hour=shown_commits["authored_at_local"].dt.hour,
        )
        .groupby(["weekday", "hour"]).size().reset_index(name="commits")
    )
    _chart = (
        alt.Chart(_grid)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("hour:O", title="Hour of day (local time)", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("weekday:N", title=None,
                    sort=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
            color=alt.Color("commits:Q", title="Commits", scale=alt.Scale(range=GREENS[1:])),
            tooltip=["weekday:N", "hour:O", "commits:Q"],
        )
        .properties(width="container", height=210)
    )
    mo.vstack([mo.md("## When the commits happen"), _chart])
    return


@app.cell
def _(mo, shown_repos):
    _table = (
        shown_repos[~shown_repos["is_fork"].astype(bool)]
        .sort_values(["commits", "stars"], ascending=False)
        .head(12)
        .assign(pushed_at=lambda t: t["pushed_at"].dt.strftime("%Y-%m-%d"))
        [["repository_name", "description", "primary_language", "commits", "stars", "pushed_at"]]
        .rename(columns={"repository_name": "Repository", "description": "About", "primary_language": "Language",
                         "commits": "Commits", "stars": "Stars", "pushed_at": "Last push"})
        .reset_index(drop=True)
    )
    mo.vstack([
        mo.md("## Most active repositories"),
        mo.ui.table(_table, selection=None, show_column_summaries=False, show_data_types=False, pagination=False),
    ])
    return


if __name__ == "__main__":
    app.run()
