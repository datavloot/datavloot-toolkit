import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="GitHub — explore")


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
    profile = con.sql("SELECT login, name, origin, public_repos, followers, created_at FROM source.profile").df()
    mo.vstack([mo.md("## Whose data\n`origin` is *sample* until you connect your own account."),
               mo.ui.table(profile)])
    return


@app.cell
def _(con, mo):
    per_year = con.sql("""
        SELECT d.year, sum(f.contributions) AS contributions, count(*) FILTER (WHERE f.is_active) AS active_days
        FROM github_business.fct_contribution_day f
        JOIN github_business.dim_date d ON f.contribution_date_key = d.date_key
        GROUP BY ALL ORDER BY d.year
    """).df()
    mo.vstack([mo.md("## Contributions per year"), mo.ui.table(per_year)])
    return


@app.cell
def _(con, mo):
    # Weekend work, by repository: side projects tend to show here.
    weekend = con.sql("""
        SELECT r.repository_name,
               count(*) AS commits,
               round(100.0 * count(*) FILTER (WHERE d.is_weekend) / count(*), 1) AS pct_weekend
        FROM github_business.fct_commit f
        JOIN github_business.dim_date d ON f.authored_date_key = d.date_key
        LEFT JOIN github_business.dim_repository r USING (repository_key)
        GROUP BY ALL ORDER BY commits DESC
    """).df()
    mo.vstack([mo.md("## Weekday or weekend"), mo.ui.table(weekend)])
    return


@app.cell
def _(con, mo):
    recent = con.sql("""
        SELECT f.authored_at_local, r.repository_name, f.message_title
        FROM github_business.fct_commit f
        LEFT JOIN github_business.dim_repository r USING (repository_key)
        ORDER BY f.authored_at DESC LIMIT 50
    """).df()
    mo.vstack([mo.md("## Latest commits"), mo.ui.table(recent)])
    return


if __name__ == "__main__":
    app.run()
