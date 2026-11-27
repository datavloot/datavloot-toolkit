# github

A dbt project built on the [datavloot toolkit](https://github.com/datavloot/datavloot-toolkit),
on your own GitHub history: a portfolio you run yourself, and a data platform to show alongside it.

It starts on a **made-up developer**, so everything works the moment the project is created.
Connect your own account and the same tables, models, notebook and dashboard show your
repositories, languages, commits and contribution calendar. The output answers questions like:

- How active have you been over the past year, and how long was your longest streak?
- What kind of work do you do: backend, frontend, data, infrastructure?
- Which repositories carry most of your work, and when do your commits happen?

For a job interview this is two things in one: the dashboard shows your work, and the project
shows that you can build a data platform, from API to tested star schema.

---

## Getting started

```
datavloot demo --github
cd github
uv sync --python 3.12
uv run dbt deps
uv run dbt parse
uv run datavloot start --run
```

The last line starts Dagster at http://localhost:3000 and the Crows Nest at http://localhost:8080,
and runs the pipeline once on the sample. Open **Dashboards → portfolio** in the Crows Nest.

---

## Use your own GitHub data

1. Make a fine-grained personal access token at
   [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
   → **Generate new token**. Give it a name and an expiry date.
2. Under **Repository access**, choose **All repositories** to include your private ones, or
   **Public repositories** for public work only. Under **Permissions → Repositories**, set
   **Contents** and **Metadata** to **Read-only**. Nothing else is needed: the token cannot change
   anything.
3. In this folder, run:
   ```
   uv run python -m github_platform.connect
   ```
   It asks for your username and the token, hides the token while you type it, saves both in
   `.env` (which git ignores), and checks that GitHub accepts them.
4. In the Crows Nest, **Pipelines → Materialize all**. Then restart Datavloot
   (`uv run datavloot start`) to switch on the `github_refresh_daily` schedule, which refreshes
   everything every morning at 07:00.

The first run takes a few minutes for someone with many repositories. It covers your 100 most
recently pushed repositories, and up to 2,000 of your commits in each.

**Before you show it to anyone:** the dashboard leaves private repositories out unless you switch
them on, and the contribution calendar counts private work without saying what it was. The
notebook and the tables do show private repository names and commit messages.

To go back to the sample, remove `GITHUB_TOKEN` from `.env` and run the pipeline again. Revoke the
token on GitHub when you no longer need it.

---

## What this project demonstrates

- A REST and a GraphQL API through dlt with a token kept in `.env`, wrapped in a Dagster asset
  (`github_platform/`)
- History that outlives its source: commits merge on their sha, so they stay when a repository goes
- A sample that runs through exactly the same code as the real data, with one `origin` switch
  (`macros/stage_github.sql`)
- A seed that turns twenty languages into a story (`seeds/language_areas.csv`)
- Facts at three grains: per commit, per day, per repository and language
- Data quality tests at every layer, including a calendar with no missing days

---

## Project structure

```
apps/
└── portfolio.py                # dashboard for the Crows Nest's Dashboards tab (marimo run, no code)
github_platform/
├── assets.py                   # the dlt and dbt assets, and the daily schedule
├── github.py                   # the GitHub APIs and the rows they become
├── sample.py                   # the made-up developer
└── connect.py                  # saving and checking your token
macros/
└── stage_github.sql            # stages a table, keeping the sample's or your own rows
models/
├── source/github/              # stg_github__*: one per table, ephemeral
└── business/
    ├── dimensions/             # dim_repository, dim_language, dim_date, dim_time
    └── facts/                  # fct_commit, fct_contribution_day, fct_repository_language
notebooks/
└── explore_github.py           # marimo notebook to explore the lake
seeds/
└── language_areas.csv          # which area of work each language stands for; make it yours
```

Your time zone is `github_timezone` in `dbt_project.yml` (default `Europe/Amsterdam`).
