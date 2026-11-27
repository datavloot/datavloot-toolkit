"""
Spotify for this project: the settings in .env, the Web API, and the rows the pipeline loads.

Until an account is connected (`uv run python -m spotify_platform.connect`), the
pipeline reads from `sample.SampleSpotify` instead, which answers the same calls
with made-up listening history. Both go through the same `*_row` functions, so
the tables look the same either way.

Written for the Web API as Development Mode apps get it since February 2026:
no popularity, follower counts or batch lookups (/tracks?ids=, /artists?ids=),
and a playlist's tracks under /playlists/{id}/items, for playlists the user owns
or collaborates on only.
"""

import os
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import dotenv_values

PROJECT_DIR = Path(__file__).parent.parent
ENV_FILE = PROJECT_DIR / ".env"

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
# Spotify no longer accepts http://localhost: a loopback address it does.
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = (
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-follow-read",
)
TIME_RANGES = ("short_term", "medium_term", "long_term")
PAGE_SIZE = 50  # the largest page every endpoint used here accepts


def setting(name: str) -> str | None:
    """
    A setting from .env, read again on every call.

    Not from os.environ first: a process started before `connect` ran, or
    before Spotify handed out a new refresh token, inherits the old value.
    """
    value = dotenv_values(ENV_FILE).get(name) if ENV_FILE.is_file() else None
    return value or os.environ.get(name) or None


def set_setting(name: str, value: str) -> None:
    """Write one setting to .env, replacing its line or adding one."""
    if any(c.isspace() or c in "#'\"" for c in value):
        raise ValueError(f"{name}: unexpected characters in the value Spotify returned")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
    line = f"{name}={value}"
    for i, existing in enumerate(lines):
        if existing.split("=", 1)[0].strip().removeprefix("export ").strip() == name:
            lines[i] = line
            break
    else:
        lines.append(line)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def connected() -> bool:
    return bool(setting("SPOTIFY_REFRESH_TOKEN") and setting("SPOTIFY_CLIENT_ID"))


class Spotify:
    """The Web API for one user, through a refresh token from `connect`."""

    origin = "spotify"

    def __init__(self, http, client_id: str, refresh_token: str):
        # http: requests, or dlt's requests helper, which retries on 429 and
        # 5xx and waits as long as Retry-After asks.
        self._http = http
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._access_token = None
        self._expires = 0.0

    def _token(self) -> str:
        if self._access_token and time.time() < self._expires - 60:
            return self._access_token
        response = self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
            },
        )
        if response.status_code == 400:
            raise RuntimeError(
                "Spotify refused the saved login (it was revoked, or the app's client ID changed). "
                "Connect again: uv run python -m spotify_platform.connect"
            )
        response.raise_for_status()
        token = response.json()
        self._access_token = token["access_token"]
        self._expires = time.time() + token.get("expires_in", 3600)
        # PKCE refresh tokens can rotate: the old one stops working once a new one is issued.
        if token.get("refresh_token") and token["refresh_token"] != self._refresh_token:
            self._refresh_token = token["refresh_token"]
            set_setting("SPOTIFY_REFRESH_TOKEN", self._refresh_token)
        return self._access_token

    def get(self, path: str, **params) -> dict:
        url = path if path.startswith("https://") else f"{API_URL}{path}"
        response = self._http.get(
            url, params=params or None, headers={"Authorization": f"Bearer {self._token()}"}
        )
        response.raise_for_status()
        return response.json()

    def pages(self, path: str, key: str | None = None, **params):
        """Every item of a paged list, following `next`; `key` for a list wrapped in an object."""
        page = self.get(path, limit=PAGE_SIZE, **params)
        while True:
            if key:
                page = page[key]
            yield from page.get("items") or []
            if not page.get("next"):
                return
            page = self.get(page["next"])


def client(http):
    """The user's Spotify once connected, the sample until then."""
    if connected():
        return Spotify(http, setting("SPOTIFY_CLIENT_ID"), setting("SPOTIFY_REFRESH_TOKEN"))
    from .sample import SampleSpotify

    return SampleSpotify()


# --- Rows ---------------------------------------------------------------------
# Flat rows: dlt would turn the artist lists into child tables of their own.


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def track_row(track: dict) -> dict:
    album = track.get("album") or {}
    artists = track.get("artists") or [{}]
    return {
        "track_id": track["id"],
        "track_name": track.get("name"),
        "duration_ms": track.get("duration_ms"),
        "is_explicit": track.get("explicit"),
        "album_id": album.get("id"),
        "album_name": album.get("name"),
        "album_release_date": album.get("release_date"),
        "artist_id": artists[0].get("id"),
        "artist_name": artists[0].get("name"),
        "artist_names": ", ".join(a["name"] for a in artists if a.get("name")),
    }


def artist_row(artist: dict) -> dict:
    return {
        "artist_id": artist["id"],
        "artist_name": artist.get("name"),
        # Spotify still sends genres, but for many artists the list is empty.
        "genres": ", ".join(artist.get("genres") or []) or None,
    }


def _is_track(item: dict | None) -> bool:
    # A playlist can hold podcast episodes and local files, which have no Spotify ID or album.
    return bool(item and item.get("id") and item.get("type", "track") == "track")


def account(sp) -> list[dict]:
    me = sp.get("/me")
    return [{"user_id": me["id"], "display_name": me.get("display_name"), "origin": sp.origin}]


def recently_played(sp):
    # The API keeps only the last 50 plays, so history builds up run by run;
    # the schedule in assets.py runs often enough not to miss any.
    for item in sp.get("/me/player/recently-played", limit=PAGE_SIZE).get("items") or []:
        if not _is_track(item.get("track")):
            continue
        context = item.get("context") or {}
        yield {
            "played_at": _timestamp(item["played_at"]),
            **track_row(item["track"]),
            "context_type": context.get("type"),
            "origin": sp.origin,
        }


def top_tracks(sp, today: date):
    for time_range in TIME_RANGES:
        for rank, track in enumerate(sp.pages("/me/top/tracks", time_range=time_range), start=1):
            yield {"snapshot_date": today, "time_range": time_range, "rank": rank,
                   **track_row(track), "origin": sp.origin}


def top_artists(sp, today: date):
    for time_range in TIME_RANGES:
        for rank, artist in enumerate(sp.pages("/me/top/artists", time_range=time_range), start=1):
            yield {"snapshot_date": today, "time_range": time_range, "rank": rank,
                   **artist_row(artist), "origin": sp.origin}


def saved_tracks(sp):
    for item in sp.pages("/me/tracks"):
        if _is_track(item.get("track")):
            yield {"added_at": _timestamp(item.get("added_at")), **track_row(item["track"]), "origin": sp.origin}


def _own_playlists(sp, user_id: str):
    for playlist in sp.pages("/me/playlists"):
        owner = playlist.get("owner") or {}
        # `tracks` was renamed `items` in February 2026; older answers still say tracks.
        count = (playlist.get("items") or playlist.get("tracks") or {}).get("total")
        yield playlist, {
            "playlist_id": playlist["id"],
            "playlist_name": playlist.get("name"),
            "owner_name": owner.get("display_name"),
            "is_own": owner.get("id") == user_id or bool(playlist.get("collaborative")),
            "is_public": playlist.get("public"),
            "is_collaborative": playlist.get("collaborative"),
            "track_count": count,
            "origin": sp.origin,
        }


def playlists(sp, user_id: str):
    for _, row in _own_playlists(sp, user_id):
        yield row


def playlist_items(sp, user_id: str):
    # Only for playlists the user owns or collaborates on: Spotify no longer
    # lists the tracks of anyone else's.
    for playlist, row in _own_playlists(sp, user_id):
        if not row["is_own"]:
            continue
        for position, item in enumerate(sp.pages(f"/playlists/{playlist['id']}/items")):
            track = item.get("item") or item.get("track")
            if _is_track(track):
                yield {"playlist_id": playlist["id"], "position": position,
                       "added_at": _timestamp(item.get("added_at")), **track_row(track), "origin": sp.origin}


def followed_artists(sp):
    for artist in sp.pages("/me/following", key="artists", type="artist"):
        yield {**artist_row(artist), "origin": sp.origin}
