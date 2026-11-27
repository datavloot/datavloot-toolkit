"""
Made-up listening history, so the demo runs before any account is connected.

`SampleSpotify` answers the calls spotify.py makes with the Web API's own
shapes, so the sample goes through the same code as real data. Every artist,
album and track here is invented. The history covers the last 90 days up to
now and is generated from a fixed seed: the same habits on every run, moved
along with the calendar. The pipeline replaces the sample tables on each run
(assets.py), so the days moving on never pile up duplicates.
"""

import random
from datetime import datetime, timedelta, timezone

SEED = 20261127
DAYS = 90

# (artist, genres, album, tracks): a listener with a few favourites and a long tail.
CATALOGUE = [
    ("Harbour Lights", ["indie pop"], "Low Tide Letters",
     ["Paper Boats", "Lighthouse Keeper", "Salt in the Air", "Mooring", "Last Ferry Home", "Brackish"]),
    ("Copper Kites", ["indie rock"], "Weather Vane",
     ["Crosswind", "Rust Belt Summer", "Tin Roof", "Gale Warning", "Kite String", "Static Bloom"]),
    ("Lumen Drift", ["synthwave", "electronic"], "Night Shift Neon",
     ["Afterglow Avenue", "Overpass", "Cathode Dreams", "Tail Lights", "4 AM Arcade", "Chrome Rain"]),
    ("Quiet Engine", ["lo-fi", "chillhop"], "Desk Plants",
     ["Morning Pages", "Steam Kettle", "Deep Focus", "Pencil Shavings", "Window Seat", "Slow Commit"]),
    ("Velvet Meridian", ["neo soul"], "Golden Hour Hotel",
     ["Room 204", "Honey Static", "Velvet Rope", "Late Checkout", "Marigold", "Elevator Love"]),
    ("Northbound Static", ["electronic", "house"], "Signal Fires",
     ["Pulse Check", "Northern Line", "Frequency", "Tunnel Vision", "Open Circuit", "Daybreak Edit"]),
    ("The Paper Lanterns", ["folk"], "Kindling",
     ["Woodsmoke", "Riverbend", "The Long Walk", "Small Hours", "Orchard Gate", "Ember"]),
    ("Brass Atlas", ["jazz"], "Map of the Blues",
     ["Compass Rose", "Meridian Swing", "Equator", "Trade Winds", "Longitude", "Blue Latitude"]),
    ("Neon Orchard", ["dance pop"], "Fruit Machine",
     ["Cherry Bomb Pop", "Sugar Rush Hour", "Disco Pear", "Lemonade Lights", "Peach Fuzz", "Glitter Seeds"]),
    ("Saltwater Choir", ["ambient"], "Tidal Hymns",
     ["Undertow", "Sea Glass", "Fathom", "Horizon Line", "Kelp Forest", "Slack Water"]),
    ("Midnight Ferry", ["alt country"], "Two Shores",
     ["Gravel Road", "Ferry Lights", "Dust and Diesel", "Porch Light", "County Line", "Crossing"]),
    ("Glass Harbor Quartet", ["classical", "chamber"], "Four Seasons in Port",
     ["Allegro for Cranes", "Adagio at Dusk", "Scherzo of Gulls", "Rondo of the Docks", "Nocturne", "Coda"]),
]

# How much this listener plays each artist, favourites first.
ARTIST_WEIGHTS = [16, 11, 10, 9, 7, 6, 5, 4, 3, 3, 2, 1]

# What they put on at which hour (local time): artist indexes favoured per moment.
MOODS = {
    "morning": [0, 6, 4, 1],          # waking up, commute
    "daytime": [3, 9, 7, 11],         # focus music at work
    "evening": [0, 1, 4, 8, 10],      # cooking, going out
    "late": [2, 5, 9, 3],             # late evening, night
}
# How much is played per hour of the day on a weekday and at the weekend,
# scaled by PLAYS_PER_WEIGHT.
PLAYS_PER_WEIGHT = 0.4
WEEKDAY = [1, 0, 0, 0, 0, 0, 2, 9, 10, 5, 4, 4, 3, 4, 5, 5, 4, 7, 8, 6, 5, 6, 5, 3]
WEEKEND = [3, 2, 1, 0, 0, 0, 0, 1, 2, 4, 6, 6, 5, 5, 5, 6, 6, 5, 6, 7, 8, 8, 7, 5]
# The sample listener lives one hour ahead of UTC, like Amsterdam in winter.
UTC_OFFSET_HOURS = 1


def _mood(hour: int) -> str:
    if 6 <= hour < 9:
        return "morning"
    if 9 <= hour < 17:
        return "daytime"
    if 17 <= hour < 21:
        return "evening"
    return "late"


class SampleSpotify:
    origin = "sample"

    def __init__(self, now: datetime | None = None):
        self._now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        rnd = random.Random(SEED)
        self._artists, self._tracks = [], []
        for a, (artist, genres, album, titles) in enumerate(CATALOGUE):
            artist_obj = {"id": f"sampleartist{a:02d}", "name": artist, "genres": genres, "type": "artist"}
            self._artists.append(artist_obj)
            album_obj = {"id": f"samplealbum{a:02d}", "name": album,
                         "release_date": f"{2014 + a}-{(a % 12) + 1:02d}-15"}
            for t, title in enumerate(titles):
                self._tracks.append({
                    "id": f"sampletrack{a:02d}{t}", "name": title, "type": "track",
                    "duration_ms": rnd.randint(150, 330) * 1000, "explicit": rnd.random() < 0.1,
                    "album": album_obj, "artists": [{"id": artist_obj["id"], "name": artist}],
                })
        self._plays = self._history(rnd)
        self._saved = self._library(rnd)
        self._playlists = self._make_playlists(rnd)

    def _track_of(self, rnd: random.Random, hour: int) -> dict:
        favoured = MOODS[_mood(hour)]
        weights = [w * (4 if i in favoured else 1) for i, w in enumerate(ARTIST_WEIGHTS)]
        artist = rnd.choices(range(len(CATALOGUE)), weights)[0]
        # Within an artist, the first tracks are the ones that stuck.
        return self._tracks[artist * 6 + rnd.choices(range(6), [6, 5, 4, 3, 2, 1])[0]]

    def _history(self, rnd: random.Random) -> list[dict]:
        plays = []
        start = (self._now - timedelta(days=DAYS)).replace(hour=0, minute=0, second=0)
        for day in range(DAYS + 1):
            midnight = start + timedelta(days=day)
            per_hour = WEEKEND if midnight.weekday() >= 5 else WEEKDAY
            for hour, weight in enumerate(per_hour):
                # About 40 plays on a weekday: a couple of hours of music.
                expected = weight * PLAYS_PER_WEIGHT
                count = max(0, round(rnd.gauss(expected, expected / 3))) if expected else 0
                at = midnight + timedelta(hours=hour - UTC_OFFSET_HOURS, minutes=rnd.randint(0, 20))
                for _ in range(count):
                    track = self._track_of(rnd, hour)
                    at += timedelta(milliseconds=track["duration_ms"]) + timedelta(seconds=rnd.randint(0, 40))
                    if at > self._now:
                        break
                    plays.append({
                        "track": track,
                        "played_at": at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "context": {"type": rnd.choice(["playlist", "playlist", "album", "artist"])},
                    })
        plays.sort(key=lambda p: p["played_at"], reverse=True)  # newest first, as the API answers
        return plays

    def _library(self, rnd: random.Random) -> list[dict]:
        saved = rnd.sample(self._tracks, 32)
        return [
            {"added_at": (self._now - timedelta(days=rnd.randint(1, 700), minutes=rnd.randint(0, 1440)))
             .strftime("%Y-%m-%dT%H:%M:%SZ"), "track": track}
            for track in saved
        ]

    def _make_playlists(self, rnd: random.Random) -> list[tuple[dict, list[dict]]]:
        made = []
        for p, (name, mood) in enumerate([
            ("Morning commute", "morning"), ("Deep focus", "daytime"),
            ("Kitchen disco", "evening"), ("After midnight", "late"),
        ]):
            hour = {"morning": 7, "daytime": 11, "evening": 19, "late": 23}[mood]
            tracks = list({t["id"]: t for t in (self._track_of(rnd, hour) for _ in range(30))}.values())[:15]
            playlist = {"id": f"sampleplaylist{p}", "name": name, "public": p % 2 == 0, "collaborative": False,
                        "owner": {"id": "sample", "display_name": "Sample listener"},
                        "items": {"total": len(tracks)}}
            items = [{"added_at": (self._now - timedelta(days=rnd.randint(1, 300))).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "item": t} for t in tracks]
            made.append((playlist, items))
        # One a friend made: Spotify lists it, but not its tracks.
        made.append(({"id": "sampleplaylistfriend", "name": "Road trip (from a friend)", "public": True,
                      "collaborative": False, "owner": {"id": "friend", "display_name": "A friend"},
                      "items": {"total": 48}}, []))
        return made

    def _top(self, kind: str, time_range: str) -> list[dict]:
        days = {"short_term": 28, "medium_term": 182, "long_term": 3650}[time_range]
        since = (self._now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        counts: dict[str, int] = {}
        for play in self._plays:
            if play["played_at"] >= since:
                key = play["track"]["id"] if kind == "tracks" else play["track"]["artists"][0]["id"]
                counts[key] = counts.get(key, 0) + 1
        objects = {t["id"]: t for t in self._tracks} if kind == "tracks" else {a["id"]: a for a in self._artists}
        return [objects[key] for key, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:50]

    # --- The calls spotify.py makes ---------------------------------------------

    def get(self, path: str, **params) -> dict:
        if path == "/me":
            return {"id": "sample", "display_name": "Sample listener"}
        if path == "/me/player/recently-played":
            # All 90 days at once, where the API gives only the last 50: a
            # sample shows a history that a real account builds up run by run.
            return {"items": self._plays, "next": None}
        raise KeyError(path)

    def pages(self, path: str, key: str | None = None, **params):
        if path in ("/me/top/tracks", "/me/top/artists"):
            yield from self._top(path.rsplit("/", 1)[1], params["time_range"])
        elif path == "/me/tracks":
            yield from self._saved
        elif path == "/me/playlists":
            yield from (playlist for playlist, _ in self._playlists)
        elif path.startswith("/playlists/"):
            playlist_id = path.split("/")[2]
            yield from next(items for playlist, items in self._playlists if playlist["id"] == playlist_id)
        elif path == "/me/following":
            yield from (self._artists[i] for i in (0, 1, 3, 4, 7, 9))
        else:
            raise KeyError(path)
