# spotify

A dbt project built on the [datavloot toolkit](https://github.com/datavloot/datavloot-toolkit),
on data you know better than anyone: your own Spotify listening.

It starts on **made-up sample data** (90 days of an invented listener with invented artists), so
everything works the moment the project is created. Connect your own account and the same tables,
models, notebook and dashboard show your plays instead. The output answers questions like:

- At what hour of which day do you listen most?
- Who is your soundtrack for the morning commute, and who for late evenings?
- Which Liked Songs have you not played in weeks?

---

## Getting started

```
datavloot demo --spotify
cd spotify
uv sync --python 3.12
uv run dbt deps
uv run dbt parse
uv run datavloot start --run
```

The last line starts Dagster at http://localhost:3000 and the Crows Nest at http://localhost:8080,
and runs the pipeline once on the sample. Open **Dashboards → listening_habits** in the Crows Nest.

---

## Use your own Spotify data

This needs a Spotify developer app, which takes five minutes. Spotify's rules for these apps
(Development Mode, February 2026): the **app owner needs Spotify Premium**, and an app has at most
five users. That is plenty for yourself, but it is why this cannot be a ready-made app.

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), log in and
   click **Create app**. Any name and description will do.
2. Under **Redirect URIs** add exactly `http://127.0.0.1:8888/callback` (Spotify does not accept
   `localhost`). Under **Which API/SDKs are you planning to use?** tick **Web API**. Save.
3. Open the app's **Settings** and copy the **Client ID**. No client secret is needed: the login
   uses PKCE.
4. In this folder, run:
   ```
   uv run python -m spotify_platform.connect
   ```
   It asks for the Client ID, opens Spotify's login in the browser and saves a refresh token in
   `.env`. That file stays on your machine and git ignores it.
5. In the Crows Nest, **Pipelines → Materialize all**. Then restart Datavloot
   (`uv run datavloot start`): from then on the `spotify_sync_every_30_minutes` schedule collects
   your plays.

**Spotify only hands out your last 50 plays.** Your history in this project starts on the day you
connect and grows while Datavloot runs, every 30 minutes. Your top tracks and artists, Liked Songs,
playlists and followed artists are there from the first run. For years of history, Spotify's
privacy page lets you request your *Extended streaming history* export. Loading it is a good next
step to build with your AI assistant.

To go back to the sample, remove `SPOTIFY_REFRESH_TOKEN` from `.env` and run the pipeline again. To
disconnect for good, also remove the app under **Apps** in your Spotify account settings.

---

## What this project demonstrates

- An API source with OAuth (PKCE) through dlt, wrapped in a Dagster asset (`spotify_platform/`)
- History from an API that only gives the latest: merging run by run on a schedule
- A sample that runs through exactly the same code as the real data, with one `origin` switch
  (`macros/stage_spotify.sql`)
- Dimensions built from several sources at once (`dim_track`, `dim_artist`) with toolkit macros
- A fact in local time with a seed-driven grouping (`fct_play`, `seeds/listening_moments.csv`)
- Data quality tests at every layer

---

## Project structure

```
apps/
└── listening_habits.py       # dashboard for the Crows Nest's Dashboards tab (marimo run, no code)
spotify_platform/
├── assets.py                 # the dlt and dbt assets, and the 30-minute schedule
├── spotify.py                # the Web API and the rows it becomes
├── sample.py                 # the made-up listener
└── connect.py                # logging in once: uv run python -m spotify_platform.connect
macros/
└── stage_spotify.sql         # stages a table, keeping the sample's or your own rows
models/
├── source/spotify/           # stg_spotify__*: one per table, ephemeral
└── business/
    ├── dimensions/           # dim_track, dim_artist, dim_playlist, dim_listening_moment, dim_date, dim_time
    └── facts/                # fct_play: one row per play
notebooks/
└── explore_spotify.py        # marimo notebook to explore the lake
seeds/
└── listening_moments.csv     # the parts of your day; change them to fit yours
```

Your time zone is `spotify_timezone` in `dbt_project.yml` (default `Europe/Amsterdam`).

---

## Your data

Everything stays on this machine: the lake in `lake/`, the token in `.env`. The pipeline only
reads from Spotify, with read-only scopes: recently played, top items, library, playlists, follows.
Hand `data-instructions.md` to your AI assistant at the start of a session so it knows the
project's conventions. Do not paste your data into a chat you would not want kept.
