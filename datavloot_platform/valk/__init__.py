"""
The Valk: a datavloot project deployed as a client project on an SRDP Compose stack.

`render` turns datavloot.yml into a `deploy/valk/` directory (Compose overlay,
Dockerfiles, dbt target, runbook). `commands` fetches the pinned SRDP checkout and
drives `docker compose` with the two stacks layered. Nothing here needs Docker at
import or render time, so the rendering is unit-tested without it.
"""
