# One image for every Optimist service: Dagster (webserver and daemon), the
# Crows Nest and Marimo. Built from this checkout, with the versions in uv.lock,
# so the VM runs exactly what CI tested. Build context: the repository root.

FROM python:3.12-slim

# git: dbt deps fetches the optimist dbt package from a git repository.
# tini: forwards signals, so `docker compose stop` stops Dagster cleanly.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

# uid 1000: the deploy user that owns /srv/optimist on the VM (see deploy/thalassa).
RUN useradd --create-home --uid 1000 optimist

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY datavloot_platform ./datavloot_platform
RUN uv sync --locked --extra optimist --no-dev --no-editable \
 && rm -rf /root/.cache

COPY deploy/compose/prepare.sh /usr/local/bin/optimist-prepare
RUN chmod 0755 /usr/local/bin/optimist-prepare \
 && install -d -o optimist -g optimist /dagster_home /srv/optimist

USER optimist

# DuckDB downloads extensions on first use; do it now, so a running service
# never stalls on a download (see datavloot_platform/extensions.py).
RUN python -c "import duckdb; from datavloot_platform import extensions; \
failures = extensions.install(duckdb.connect()); assert not failures, failures"

ENV DAGSTER_HOME=/dagster_home
WORKDIR /srv/optimist

ENTRYPOINT ["tini", "--"]
