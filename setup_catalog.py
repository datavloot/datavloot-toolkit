"""
Initialize the DuckLake catalog with medallion architecture schemas.

Run once from the project root before starting Dagster:
    python setup_catalog.py
"""

import duckdb
import os

CATALOG_DB = "data/catalog.duckdb"


def main():
    os.makedirs("data", exist_ok=True)

    con = duckdb.connect()

    print("Installing DuckLake extension...")
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")

    print(f"Creating DuckLake catalog at '{CATALOG_DB}'...")
    con.execute(f"ATTACH '{CATALOG_DB}' AS lakehouse (TYPE ducklake, AUTOMATIC_MIGRATION TRUE)")

    print("Creating schemas...")
    con.execute("CREATE SCHEMA IF NOT EXISTS lakehouse.source")
    con.execute("CREATE SCHEMA IF NOT EXISTS lakehouse.business")

    schemas = con.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE catalog_name = 'lakehouse'"
    ).fetchall()
    print(f"Schemas ready: {[s[0] for s in schemas]}")

    con.close()
    print("\nDone! Run 'dagster dev' to start the platform.")


if __name__ == "__main__":
    main()
