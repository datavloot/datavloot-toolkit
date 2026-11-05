"""
Where Dagster is in starting up, for the Crows Nest to say so.

`datavloot start` starts the Crows Nest straight away and Dagster next to it,
because Dagster takes half a minute or more to load a project, and a person
who double-clicked a shortcut should see the Crows Nest within seconds rather
than nothing at all. Meanwhile a probe that finds Dagster not answering cannot
tell "still loading" from "not running"; this tells it, so the health check
can say "starting" and, if loading fails, why.

One process, one Dagster: module-level state, set by cli._start's watcher
thread and read by the health check. `datavloot launch` on its own never sets
it, so there the probe decides alone, as before.
"""

import threading

_lock = threading.Lock()
_state: dict = {"dagster": None, "error": None}


def set_dagster(status: str | None, error: str | None = None) -> None:
    """status: "starting", "ready" or "failed", or None when nothing is known."""
    with _lock:
        _state["dagster"] = status
        _state["error"] = error


def dagster() -> tuple[str | None, str | None]:
    """(status, error) as last set."""
    with _lock:
        return _state["dagster"], _state["error"]
