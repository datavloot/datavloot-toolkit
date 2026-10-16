#!/bin/sh
# Runs once before the services start (the `prepare` service): makes sure the
# project exists, and does what `dagster dev` does on a laptop before loading it.
set -eu

: "${PROJECT_DIR:?PROJECT_DIR is not set}"

if [ ! -f "$PROJECT_DIR/dbt_project.yml" ]; then
    if [ "${FALCON_DEMO:-0}" = "1" ]; then
        # Docker creates the other services' working directory, empty, before
        # this runs; `datavloot demo` refuses a directory that exists.
        rmdir "$PROJECT_DIR" 2>/dev/null || true
        datavloot demo "$PROJECT_DIR"
    else
        echo "No dbt project at $PROJECT_DIR. Put the project there, or set FALCON_DEMO=1 for the NOAA demo." >&2
        exit 1
    fi
fi

cd "$PROJECT_DIR"

# The project's instance settings (the lake pool, see dagster.yaml) only apply
# from DAGSTER_HOME.
cp dagster.yaml "$DAGSTER_HOME/dagster.yaml"

# Dagster loads the dbt assets from target/manifest.json; outside `dagster dev`
# nothing builds it on the fly.
dbt deps
dbt parse --target prod
