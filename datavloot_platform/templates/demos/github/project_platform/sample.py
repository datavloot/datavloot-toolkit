"""
A made-up developer, so the demo runs before any account is connected.

`SampleGitHub` answers the calls github.py makes with GitHub's own shapes, so
the sample goes through the same code as real data. The person, the
repositories and the commits are invented; the history runs up to today and
comes from a fixed seed, so every run tells the same story. The pipeline
replaces the sample tables on each run (assets.py).
"""

import hashlib
import random
from datetime import date, datetime, timedelta, timezone

SEED = 20261127
USERNAME = "sample-dev"
YEARS = 2.5

# (name, description, languages with their share, topics, stars, start: days ago, end: days ago, weight)
REPOSITORIES = [
    ("tide-tables", "Tide predictions for Dutch harbours as a small REST API",
     {"Python": 0.82, "Dockerfile": 0.03, "Shell": 0.15}, ["fastapi", "api", "open-data"], 41, 900, 120, 5),
    ("bike-commute-stats", "Strava-free cycling stats from GPX files, with a marimo dashboard",
     {"Python": 0.9, "SQL": 0.1}, ["duckdb", "data", "marimo"], 17, 700, 0, 6),
    ("portfolio-site", "My personal site", {"TypeScript": 0.6, "CSS": 0.25, "HTML": 0.15},
     ["nextjs", "portfolio"], 3, 910, 10, 2),
    ("dotfiles", "Shell, editor and terminal setup", {"Shell": 0.7, "Lua": 0.3}, [], 9, 910, 30, 1),
    ("recipe-scaler", "Scales recipes and converts units; a weekend project",
     {"Go": 0.95, "Makefile": 0.05}, ["cli", "go"], 6, 520, 380, 3),
    ("warehouse-in-a-box", "dbt + DuckDB starter for small teams", {"SQL": 0.55, "Python": 0.4, "Jinja": 0.05},
     ["dbt", "duckdb", "analytics-engineering"], 128, 420, 0, 7),
    ("advent-of-code", "Puzzles, every December", {"Rust": 0.85, "Python": 0.15}, ["advent-of-code"], 2, 900, 0, 0),
    ("terraform-homelab", "My homelab as code", {"HCL": 0.85, "Shell": 0.15}, ["terraform", "homelab"], 11, 300, 60, 2),
]

MESSAGES = [
    "Add {thing}", "Fix {thing}", "Refactor {thing}", "Test {thing}", "Document {thing}",
    "Speed up {thing}", "Handle empty {thing}", "Rename {thing}", "Remove unused {thing}",
]
THINGS = ["the parser", "date handling", "the CLI flags", "error messages", "the README", "CI",
          "the config loader", "pagination", "time zones", "the cache", "logging", "the Dockerfile",
          "incremental loads", "the tests", "type hints", "the release script"]


def _sha(rnd: random.Random) -> str:
    return hashlib.sha1(str(rnd.random()).encode()).hexdigest()


class SampleGitHub:
    origin = "sample"
    username = USERNAME

    def __init__(self, now: datetime | None = None):
        self._now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        rnd = random.Random(SEED)
        start = self._now - timedelta(days=int(365 * YEARS))
        self._repos, self._languages, self._commits = [], {}, {}
        for i, (name, description, languages, topics, stars, begin, end, _) in enumerate(REPOSITORIES):
            full = f"{USERNAME}/{name}"
            created = self._now - timedelta(days=begin, hours=rnd.randint(0, 23))
            self._repos.append({
                "id": 9000 + i, "name": name, "full_name": full, "description": description,
                "language": max(languages, key=languages.get), "topics": topics, "fork": False,
                "private": name in ("dotfiles", "terraform-homelab"), "archived": name == "recipe-scaler",
                "stargazers_count": stars, "forks_count": stars // 8, "homepage": None,
                "html_url": f"https://github.com/{full}", "created_at": self._iso(created),
            })
            size = rnd.randint(40, 400) * 1000
            self._languages[full] = {lang: int(size * share) for lang, share in languages.items()}
            self._commits[full] = []
        # One fork: shown as a repository, left out of languages and commits.
        self._repos.append({
            "id": 9100, "name": "dbt-utils", "full_name": f"{USERNAME}/dbt-utils",
            "description": "Fork to fix a macro", "language": "Python", "topics": [], "fork": True,
            "private": False, "archived": False, "stargazers_count": 0, "forks_count": 0, "homepage": None,
            "html_url": f"https://github.com/{USERNAME}/dbt-utils",
            "created_at": self._iso(self._now - timedelta(days=200)),
        })
        self._calendar = self._history(rnd, start)
        for repo in self._repos:
            commits = self._commits.get(repo["full_name"], [])
            last = max((c["commit"]["author"]["date"] for c in commits), default=repo["created_at"])
            repo["pushed_at"] = last
        self._repos.sort(key=lambda r: r["pushed_at"], reverse=True)

    @staticmethod
    def _iso(moment: datetime) -> str:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _history(self, rnd: random.Random, start: datetime) -> dict[date, int]:
        calendar: dict[date, int] = {}
        day = start.replace(hour=0, minute=0, second=0)
        while day <= self._now:
            weekend = day.weekday() >= 5
            december = day.month == 12
            # Some weeks are busy, most are steady, a few are holidays.
            mood = rnd.random()
            busy = 0 if mood < 0.18 else (2.2 if mood > 0.9 else 1.0)
            active = [
                (full, w) for (name, _, _, _, _, begin, end, w), full
                in zip(REPOSITORIES, [f"{USERNAME}/{r[0]}" for r in REPOSITORIES])
                if (self._now - timedelta(days=begin)) <= day <= (self._now - timedelta(days=end))
            ]
            if december:
                active.append((f"{USERNAME}/advent-of-code", 8))
            commits_today = 0
            weights = [w for _, w in active if w]
            if weights:
                expected = (1.8 if weekend else 2.6) * busy
                count = max(0, round(rnd.gauss(expected, expected / 2))) if expected else 0
                for _ in range(count):
                    full = rnd.choices([f for f, w in active if w], weights)[0]
                    # Evenings on weekdays, late mornings at the weekend.
                    hour = rnd.choice([10, 11, 13, 14, 15, 16]) if weekend else rnd.choice(
                        [9, 10, 11, 12, 14, 15, 16, 19, 20, 20, 21, 21, 22, 23])
                    at = day + timedelta(hours=hour - 1, minutes=rnd.randint(0, 59), seconds=rnd.randint(0, 59))
                    if at > self._now:
                        continue
                    message = rnd.choice(MESSAGES).format(thing=rnd.choice(THINGS))
                    self._commits[full].append({
                        "sha": _sha(rnd),
                        "commit": {"author": {"name": "Sample Dev", "date": self._iso(at)}, "message": message},
                    })
                    commits_today += 1
            # Pull requests, reviews and issues count too, and so does work in private repositories.
            extra = rnd.choice([0, 0, 0, 1, 1, 2]) if not weekend and busy else 0
            calendar[day.date()] = commits_today + extra
            day += timedelta(days=1)
        for commits in self._commits.values():
            commits.sort(key=lambda c: c["commit"]["author"]["date"], reverse=True)
        return calendar

    # --- The calls github.py makes ----------------------------------------------

    def get(self, path: str, **params):
        if path == f"/users/{USERNAME}":
            return {"login": USERNAME, "name": "Sample Dev", "bio": "Data engineer. Likes tides, bikes and DuckDB.",
                    "company": None, "location": "Rotterdam", "public_repos": 7, "followers": 23,
                    "created_at": self._iso(self._now - timedelta(days=int(365 * YEARS) + 30))}
        if path.startswith("/repos/") and path.endswith("/languages"):
            return self._languages[path[len("/repos/"):-len("/languages")]]
        raise KeyError(path)

    def pages(self, path: str, max_pages: int | None = None, **params):
        if path == "/user/repos":
            yield from self._repos
        elif path.startswith("/repos/") and path.endswith("/commits"):
            yield from self._commits.get(path[len("/repos/"):-len("/commits")], [])
        else:
            raise KeyError(path)

    def graphql(self, query: str, **variables) -> dict:
        first = date.fromisoformat(variables["from"][:10])
        last = date.fromisoformat(variables["to"][:10])
        days = [{"date": d.isoformat(), "contributionCount": n} for d, n in sorted(self._calendar.items())
                if first <= d <= last]
        return {"user": {"contributionsCollection": {"contributionCalendar": {
            "weeks": [{"contributionDays": days[i:i + 7]} for i in range(0, len(days), 7)]}}}}
