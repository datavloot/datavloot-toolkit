# green_energy

A dbt project built on the [datavloot toolkit](https://github.com/datavloot/datavloot-toolkit),
on a question anyone with an electricity bill knows: **when is power cheap in the Netherlands,
and is it the wind?**

It loads the Dutch day-ahead electricity price per hour (EnergyZero) and the weather at three
places (Open-Meteo: wind, sun, temperature), from 2025-01-01 up to yesterday. Both are public
APIs: no account, no key. The output answers questions like:

- How do price and wind move together over time?
- Is there a midday "solar dip" in the price, in Dutch local time?
- How many hours had a negative price, and when?

The question, the grain decisions and the star schema are in [docs/design.md](docs/design.md).

---

## Getting started

```
datavloot demo --green_energy
cd green_energy
uv sync --python 3.12
uv run dbt deps
uv run dbt parse
uv run datavloot start --run
```

The last line starts Dagster at http://localhost:3000 and the Crows Nest at http://localhost:8080,
and runs the pipeline once. Open **Dashboards → wind_and_price** in the Crows Nest. While Datavloot
runs, the `daily_refresh` schedule adds the new day every morning at 07:00 (Amsterdam time).

---

## What this project demonstrates

- Two keyless REST APIs loaded incrementally with dlt (a cursor per source), wrapped in Dagster assets
- One seed read by both the ingestion and dbt (`seeds/locations.csv`)
- UTC as the grain and local time as an attribute, including the hours that happen twice or not at
  all when the clocks change
- Two facts at their natural grain (`fct_hourly_price`, `fct_hourly_weather`) sharing conformed
  dimensions, instead of one table without a clean grain
- Data quality tests that catch failed loads (missing hours) and time zone bugs (sun at night)

---

## Project structure

```
apps/
└── wind_and_price.py           # dashboard for the Crows Nest's Dashboards tab (marimo run, no code)
docs/
└── design.md                   # the question, sources, grain decisions and star schema
green_energy_platform/          # Dagster platform layer: the dlt assets, dbt, the daily schedule
models/
├── source/energyzero/          # stg_energyzero__day_ahead_prices: UTC and local hour
├── source/open_meteo/          # stg_open_meteo__hourly_weather
└── business/
    ├── dimensions/             # dim_location, dim_date, dim_time
    └── facts/                  # fct_hourly_price, fct_hourly_weather
notebooks/
└── explore.py                  # marimo notebook to explore the lake
seeds/
└── locations.csv               # the weather locations: coast, centre, south
tests/                          # singular tests: missing hours, future prices, sun at night
```

Add a location by adding a row to `seeds/locations.csv`: the next run fetches its weather from
2025-01-01. Hand `data-instructions.md` to your AI assistant at the start of a session so it knows
the project's conventions.
