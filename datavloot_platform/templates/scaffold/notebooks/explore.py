import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Explore — <project_name>")


@app.cell
def _():
    import marimo as mo
    import duckdb
    import altair as alt
    from pathlib import Path

    # Update this to match your project's DuckDB file name
    DB_PATH = Path(__file__).parent.parent / "<project_name>.duckdb"
    con = duckdb.connect(str(DB_PATH), read_only=True)
    mo.md(f"Connected to `{DB_PATH.name}` — {DB_PATH.stat().st_size // 1_000_000} MB")
    return DB_PATH, alt, con, mo


@app.cell
def _(con, mo):
    tables = con.sql("""
        SELECT table_schema AS schema, table_name AS table, table_type AS type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
    """).df()
    mo.vstack([
        mo.md("## Available tables"),
        mo.ui.table(tables),
    ])
    return (tables,)


@app.cell
def _(con, mo):
    # Replace with your fact table and business schema name
    SCHEMA = "<project_name>_business"
    FACT   = "fct_<event>"

    df = con.sql(f"SELECT * FROM {SCHEMA}.{FACT} LIMIT 100").df()
    mo.vstack([
        mo.md(f"## Preview — `{SCHEMA}.{FACT}`"),
        mo.ui.table(df),
    ])
    return FACT, SCHEMA, df


@app.cell
def _(FACT, SCHEMA, con, mo):
    # Edit the GROUP BY column to match a dimension in your fact table
    GROUP_BY = "<dimension_column>"

    summary = con.sql(f"""
        SELECT {GROUP_BY}, COUNT(*) AS events
        FROM {SCHEMA}.{FACT}
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 20
    """).df()
    mo.vstack([
        mo.md(f"## Events by `{GROUP_BY}`"),
        mo.ui.table(summary),
    ])
    return GROUP_BY, summary


if __name__ == "__main__":
    app.run()
