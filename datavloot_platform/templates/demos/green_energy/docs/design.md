# Green energy: design

## The question

**When is electricity cheap in the Netherlands, and why?** How do the weather (wind, sun) and
the Dutch day-ahead power price relate?

Concretely, the platform must answer:

1. How do price and wind move together over time?
2. Is there a relation between wind speed and price (scatter: wind speed vs price)?
3. What is the average price per hour of the day, in Dutch local time? (Does the sun push the
   midday price down: the "solar dip"?)
4. How many hours had a negative price, and when?
5. All of the above for a period the reader picks.

## Sources

Both are public and need no key.

| Source | Endpoint | What | Unit | Time |
|---|---|---|---|---|
| EnergyZero | `https://api.energyzero.nl/v1/energyprices` (`interval=4`, `usageType=1`, `inclBtw=false`) | Day-ahead electricity price per hour | €/kWh, excl. VAT | UTC, hour start (`readingDate`) |
| Open-Meteo archive | `https://archive-api.open-meteo.com/v1/archive` (`timezone=UTC`, `wind_speed_unit=ms`) | Hourly weather: `wind_speed_10m`, `shortwave_radiation`, `temperature_2m` | m/s, W/m², °C | UTC |

Weather for three locations, one per region:

| location_code | Name | Region | Lat | Lon |
|---|---|---|---|---|
| ijmuiden | IJmuiden | coast | 52.46 | 4.61 |
| de_bilt | De Bilt | centre | 52.10 | 5.18 |
| eindhoven | Eindhoven | south | 51.45 | 5.48 |

## Requirements

- **Period:** from 2025-01-01 up to and including yesterday. Both sources load *closed days
  only* (up to yesterday, in UTC), so a day, once loaded, is complete for both sources.
  (EnergyZero already publishes tomorrow's prices; we leave them out so price and weather cover
  the same hours.)
- **Daily refresh:** a schedule loads the new day every morning; each run only fetches what is
  new (incremental, per source).
- **Time:** stored in UTC, the time the sources use. Dutch local time (Europe/Amsterdam) is
  derived in staging, because "the hour of the day" only means something in local time: the sun
  is highest around 13:30 local time in summer.
- **Quality:** no missing hours, no duplicate hours, values in a plausible range, every fact
  row resolves to its dimensions.
- **Names in English**, units in the column name (`price_eur_kwh`, `wind_speed_10m_ms`).

## Grain decisions

| Table | Grain (one row = …) | Why |
|---|---|---|
| `fct_hourly_price` | one UTC hour | The day-ahead price is one number per hour for the whole country. |
| `fct_hourly_weather` | one UTC hour × one location | Weather differs per location; three rows per hour. |

**Two facts, not one.** The first sketch had a single hourly fact (price + wind + sun + temperature
per hour). That table has no clean grain once there are three locations: either the price is
repeated three times (and summing it is wrong), or the weather is averaged away before anyone can
see the coast vs the south. Two facts at their natural grain, sharing the same date and time
dimensions (*conformed dimensions*), keep both honest. A question that needs both ("price vs wind
at the coast") joins them on `hour_utc`, or on `date_key` + `time_key`.

**UTC as the grain, local time as an attribute.** Local hours are not unique: on the last Sunday
of October 02:00–03:00 happens twice, and on the last Sunday of March 02:00 does not happen at all.
So the facts are keyed on `hour_utc`, and carry `hour_local` plus `date_key`/`time_key` that point
at the *local* date and time of day.

## Star schema

```
                 dim_date (date_key)            dim_time (time_key)
                  ▲          ▲                      ▲          ▲
                  │          │                      │          │
   fct_hourly_price          └──── fct_hourly_weather ─────────┘
   (hour_utc)                       (hour_utc × location)
                                          │
                                          ▼
                                    dim_location (location_key)
```

### fct_hourly_price

| Column | Meaning |
|---|---|
| `fct_hourly_price_key` | Surrogate key, MD5 of `hour_utc` |
| `date_key` | FK to `dim_date`: local (Amsterdam) date, `YYYYMMDD` via `optimist.generate_date_key` |
| `time_key` | FK to `dim_time`: local hour of the day as seconds since midnight (13:00 → 46800) |
| `hour_utc` | Start of the hour, UTC |
| `hour_local` | Start of the hour, Europe/Amsterdam |
| `price_eur_kwh` | Day-ahead price, €/kWh excl. VAT |
| `is_negative_price` | `price_eur_kwh < 0` |

### fct_hourly_weather

| Column | Meaning |
|---|---|
| `fct_hourly_weather_key` | Surrogate key, MD5 of `location_code` + `hour_utc` |
| `location_key` | FK to `dim_location` |
| `date_key`, `time_key`, `hour_utc`, `hour_local` | As above |
| `wind_speed_10m_ms` | Wind speed at 10 m, m/s (instant value at the hour) |
| `shortwave_radiation_wm2` | Solar radiation on a horizontal surface, W/m² (mean over the *preceding* hour) |
| `temperature_2m_c` | Air temperature at 2 m, °C |

### Dimensions

| Dimension | Built with | Source |
|---|---|---|
| `dim_date` | `optimist.build_dim_date()` | generated, 2015–2035 |
| `dim_time` | `optimist.build_dim_time()` | generated, minute grain (1 440 rows; facts use the whole hours) |
| `dim_location` | `optimist.build_dimension()` | seed `seeds/locations.csv` |

`seeds/locations.csv` is also where the ingestion reads the coordinates from: one list of
locations for both dlt and dbt.

## Layers and names

| Layer | Schema (prod) | What |
|---|---|---|
| raw (dlt) | `source` | `day_ahead_prices`, `hourly_weather` as loaded |
| source (dbt) | `green_energy_source` | `stg_energyzero__day_ahead_prices`, `stg_open_meteo__hourly_weather`: views, UTC → local time |
| seeds | `green_energy_seeds` | `locations` |
| business | `green_energy_business` | `dim_date`, `dim_time`, `dim_location`, `fct_hourly_price`, `fct_hourly_weather` |

## Known caveats

- Since 1 October 2025 the European day-ahead market settles per 15 minutes. EnergyZero's
  `interval=4` still returns one price per hour; we take that hourly price as given.
- Open-Meteo's `shortwave_radiation` at hour *T* is the mean over *T−1h … T*; wind and
  temperature are the value at *T*. We do not shift it; at hourly resolution the effect on the
  "midday dip" is small.
- The archive's most recent days come from a preliminary reanalysis (ERA5T) and can be revised
  later. The incremental load does not re-fetch old days, so such revisions are not picked up.
