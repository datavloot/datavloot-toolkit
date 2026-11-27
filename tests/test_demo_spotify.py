"""
The Spotify demo's own code, without Spotify: the API client against a fake
HTTP layer, and the sample that stands in for an account.

spotify.py and sample.py are modules of the demo, not of the toolkit, so the
demo is built into a temporary folder and imported from there.
"""

import importlib
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from .conftest import _demo


@pytest.fixture
def platform(tmp_path, monkeypatch):
    project = _demo(tmp_path / "spotify", "spotify")
    monkeypatch.syspath_prepend(str(project))
    for name in [m for m in sys.modules if m.startswith("spotify_platform")]:
        monkeypatch.delitem(sys.modules, name)
    for name in ("SPOTIFY_CLIENT_ID", "SPOTIFY_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    spotify = importlib.import_module("spotify_platform.spotify")
    sample = importlib.import_module("spotify_platform.sample")
    return spotify, sample, project


class _Response:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Http:
    """Answers by URL; records what was asked."""

    def __init__(self, pages, tokens):
        self.pages, self.tokens, self.calls = pages, list(tokens), []

    def post(self, url, data):
        self.calls.append(("POST", data["grant_type"]))
        return _Response(self.tokens.pop(0))

    def get(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params))
        return _Response(self.pages[url])


TRACK = {"id": "t1", "name": "Song", "duration_ms": 200000, "explicit": False, "type": "track",
         "album": {"id": "a1", "name": "Album", "release_date": "2024"},
         "artists": [{"id": "r1", "name": "One"}, {"id": "r2", "name": "Two"}]}


def test_no_account_means_the_sample(platform):
    spotify, sample, _ = platform
    assert not spotify.connected()
    assert isinstance(spotify.client(http=None), sample.SampleSpotify)


def test_settings_come_from_the_env_file_as_it_is_now(platform, monkeypatch):
    """A process started before `connect` must still see the token it wrote."""
    spotify, _, project = platform
    monkeypatch.setenv("SPOTIFY_REFRESH_TOKEN", "stale")
    (project / ".env").write_text("SPOTIFY_CLIENT_ID=abc\nSPOTIFY_REFRESH_TOKEN=fresh\n", encoding="utf-8")
    assert spotify.setting("SPOTIFY_REFRESH_TOKEN") == "fresh"
    spotify.set_setting("SPOTIFY_REFRESH_TOKEN", "newer")
    text = (project / ".env").read_text(encoding="utf-8")
    assert text.count("SPOTIFY_REFRESH_TOKEN") == 1 and "SPOTIFY_REFRESH_TOKEN=newer" in text
    assert "SPOTIFY_CLIENT_ID=abc" in text and spotify.connected()


def test_a_rotated_refresh_token_is_kept(platform):
    """With PKCE Spotify may hand out a new refresh token; the old one then stops working."""
    spotify, _, project = platform
    (project / ".env").write_text("SPOTIFY_CLIENT_ID=abc\nSPOTIFY_REFRESH_TOKEN=old\n", encoding="utf-8")
    http = _Http({f"{spotify.API_URL}/me": {"id": "u1", "display_name": "Me"}},
                 [{"access_token": "x", "expires_in": 3600, "refresh_token": "rotated"}])
    sp = spotify.Spotify(http, "abc", "old")
    assert spotify.account(sp) == [{"user_id": "u1", "display_name": "Me", "origin": "spotify"}]
    assert spotify.setting("SPOTIFY_REFRESH_TOKEN") == "rotated"
    sp.get("/me")
    assert [c for c in http.calls if c[0] == "POST"] == [("POST", "refresh_token")], "token not reused"


def test_pages_follow_next_and_rows_are_flat(platform):
    spotify, _, _ = platform
    first, second = f"{spotify.API_URL}/me/tracks", "https://api.spotify.com/v1/me/tracks?offset=50"
    http = _Http({
        first: {"items": [{"added_at": "2026-01-02T03:04:05Z", "track": TRACK}], "next": second},
        second: {"items": [{"added_at": "2026-01-03T03:04:05Z", "track": None}], "next": None},
    }, [{"access_token": "x", "expires_in": 3600}])
    rows = list(spotify.saved_tracks(spotify.Spotify(http, "abc", "tok")))
    assert len(rows) == 1, "an unavailable track (null) must be skipped"
    row = rows[0]
    assert row["artist_id"] == "r1" and row["artist_names"] == "One, Two"
    assert row["added_at"] == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert all(not isinstance(v, (dict, list)) for v in row.values()), "dlt would make child tables"


def test_only_own_playlists_are_asked_for_their_items(platform):
    """Spotify no longer lists the tracks of other people's playlists (February 2026)."""
    spotify, _, _ = platform
    mine = {"id": "p1", "name": "Mine", "owner": {"id": "u1"}, "collaborative": False, "items": {"total": 1}}
    theirs = {"id": "p2", "name": "Theirs", "owner": {"id": "u2"}, "collaborative": False, "tracks": {"total": 9}}
    http = _Http({
        f"{spotify.API_URL}/me/playlists": {"items": [mine, theirs], "next": None},
        f"{spotify.API_URL}/playlists/p1/items": {"items": [{"added_at": None, "item": TRACK}], "next": None},
    }, [{"access_token": "x", "expires_in": 3600}])
    sp = spotify.Spotify(http, "abc", "tok")
    assert [r["track_count"] for r in spotify.playlists(sp, "u1")] == [1, 9]
    items = list(spotify.playlist_items(sp, "u1"))
    assert [(i["playlist_id"], i["track_id"]) for i in items] == [("p1", "t1")]
    assert not any("p2/items" in str(c) for c in http.calls)


def test_the_sample_is_the_same_every_run_and_ends_now(platform):
    spotify, sample, _ = platform
    now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    plays = list(spotify.recently_played(sample.SampleSpotify(now)))
    again = list(spotify.recently_played(sample.SampleSpotify(now)))
    assert plays == again
    assert all(p["origin"] == "sample" for p in plays)
    played = [p["played_at"] for p in plays]
    assert max(played) <= now and min(played) >= now - timedelta(days=sample.DAYS + 1)
    assert len(set(played)) == len(played), "played_at is the merge key"
    assert 20 * sample.DAYS < len(plays) < 60 * sample.DAYS


def test_the_sample_answers_every_call_the_pipeline_makes(platform):
    spotify, sample, _ = platform
    sp = sample.SampleSpotify()
    user = spotify.account(sp)[0]["user_id"]
    today = date.today()
    for rows in (spotify.top_tracks(sp, today), spotify.top_artists(sp, today), spotify.saved_tracks(sp),
                 spotify.playlists(sp, user), spotify.playlist_items(sp, user), spotify.followed_artists(sp)):
        assert list(rows), "a sample table would be empty"


def test_every_row_has_exactly_the_declared_columns(platform):
    """assets.py creates each table from spotify.TABLES, also an empty one; a column missing there would be dropped."""
    spotify, sample, _ = platform
    sp = sample.SampleSpotify()
    user, today = spotify.account(sp)[0]["user_id"], date.today()
    tables = {
        "account": spotify.account(sp), "recently_played": spotify.recently_played(sp),
        "top_tracks": spotify.top_tracks(sp, today), "top_artists": spotify.top_artists(sp, today),
        "saved_tracks": spotify.saved_tracks(sp), "playlists": spotify.playlists(sp, user),
        "playlist_items": spotify.playlist_items(sp, user), "followed_artists": spotify.followed_artists(sp),
    }
    assert set(tables) == set(spotify.TABLES)
    for table, rows in tables.items():
        assert set(next(iter(rows))) == set(spotify.TABLES[table]), table
