# VM mode: the Optimist on Docker Compose

The same platform as on a laptop, on one Linux VM, behind Traefik over HTTPS:

| URL | Service |
|---|---|
| `https://crowsnest.<DOMAIN>` | Crows Nest |
| `https://dagster.<DOMAIN>` | Dagster UI (`dagster-webserver`); `dagster-daemon` runs the schedules |
| `https://marimo.<DOMAIN>` | Marimo notebooks |

Only Traefik publishes ports (80 and 443); every service sits behind a sign-in. Certificates come
from Let's Encrypt.

The project lives on the host in `OPTIMIST_DIR/PROJECT` (default `/srv/optimist/noaa`), with
its lake in `lake/` as on a laptop. Dagster's own state (runs, schedules) is in the `dagster_home`
volume, so a schedule switched off in the UI stays off.

## Choices

- **One image for every service**, built from this checkout with the versions in `uv.lock`, so the
  VM runs what CI tested. A published release would do too, once one contains the DuckLake storage.
- **Marimo is its own service**, not started by the Crows Nest as on a laptop: one notebook server,
  reachable at its own URL. The Crows Nest links to it (`CROWSNEST_MARIMO_PUBLIC_URL`).
- **Sign-in is basic auth** in Traefik for now (`traefik/dynamic.yml`), one middleware on every
  router. Marimo runs code on the VM, so nothing may be reachable without it. Single sign-on comes
  with #20. Leave `CROWSNEST_AUTH_TOKEN` unset, or users sign in twice.

## On the VM

A VM from `deploy/thalassa` has Docker, a `deploy` user and `/srv/optimist`. DNS: a wildcard
record `*.<DOMAIN>` pointing at the server, before the first start, or Let's Encrypt fails.

```bash
ssh deploy@<ip>
git clone https://github.com/datavloot/datavloot-toolkit.git
cd datavloot-toolkit/deploy/compose

cp .env.example .env
nano .env               # DOMAIN, ACME_EMAIL; OPTIMIST_DEMO=1 for the NOAA demo
# The services run as the owner of /srv/optimist:
sed -i "s/^OPTIMIST_UID=.*/OPTIMIST_UID=$(id -u)/; s/^OPTIMIST_GID=.*/OPTIMIST_GID=$(id -g)/" .env

# A user for the sign-in; the password is asked for, not typed on the command line.
read -rsp 'Password: ' pw; echo
printf '%s\n' "$pw" | docker run --rm -i httpd:2.4-alpine htpasswd -niB <user> > traefik/users.htpasswd
unset pw

docker compose up -d --build
docker compose ps       # prepare has exited (0), the rest is running
```

More users: run the `htpasswd` line again with `>>` instead of `>`, then `docker compose restart traefik`.

Updating to a newer toolkit: `git pull`, then `docker compose up -d --build`.

## On a laptop

To try the stack without a VM, TLS or DNS (Docker Desktop):

```bash
cd deploy/compose
docker run --rm httpd:2.4-alpine htpasswd -nbB demo demo > traefik/users.htpasswd
docker compose --env-file local.env -f compose.yaml -f compose.local.yaml up -d --build
```

Then `http://crowsnest.localhost:8000` (user and password `demo`). The project lives in a Docker
volume here, not in a directory: SQLite's locking, which the lake's catalog relies on, is not
reliable on a directory shared from Windows or macOS into a container.

## Troubleshooting

- `docker compose logs prepare`: the demo, `dbt deps` and `dbt parse` run here, once per start.
- `docker compose logs traefik`: certificate and routing errors.
- `PermissionError` in `prepare`: `OPTIMIST_UID`/`OPTIMIST_GID` in `.env` do not match the owner of
  `OPTIMIST_DIR`. Fix them, then `docker compose up -d --build`.
- Traefik older than 3.6 cannot talk to Docker Engine 29 (`API returned a 400`).
