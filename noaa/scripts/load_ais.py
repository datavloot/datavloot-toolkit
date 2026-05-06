"""
One-time setup script: loads the Guam 2025 AIS CSV into the noaa.duckdb database.

Run this once from the project root before running dbt:

    python3 scripts/load_ais.py

Prerequisites: dbt-duckdb installed (pip install dbt-duckdb), which bundles duckdb.
The script creates a `raw` schema and loads seeds/guam_2025.csv into raw.guam_2025.
"""

import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'noaa.duckdb')
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'seeds', 'guam_2025.csv')

con = duckdb.connect(DB_PATH)

con.execute("CREATE SCHEMA IF NOT EXISTS raw")

print("Loading guam_2025.csv → raw.guam_2025 (3.2M rows, this may take a minute)...")
con.execute(f"""
    CREATE OR REPLACE TABLE raw.guam_2025 AS
    SELECT * FROM read_csv('{CSV_PATH}', header = true)
""")

count = con.execute("SELECT COUNT(*) FROM raw.guam_2025").fetchone()[0]
print(f"Done. Loaded {count:,} rows into raw.guam_2025.")

con.close()
