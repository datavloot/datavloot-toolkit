"""
GitHub for this project: the settings in .env, the REST and GraphQL APIs, and the rows the pipeline loads.

Until a username and token are in .env (`uv run python -m github_platform.connect`),
the pipeline reads from `sample.SampleGitHub` instead: a made-up developer with
made-up repositories. Both go through the same `*_rows` functions.

The token is a fine-grained personal access token with read-only access. With
access to public repositories only, the calendar still counts private work,
as a number per day without any detail.
"""

import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values

PROJECT_DIR = Path(__file__).parent.parent
ENV_FILE = PROJECT_DIR / ".env"

API_URL = "https://api.github.com"
PAGE_SIZE = 100
# A cap per repository, so a first run on a long-lived monorepo stays minutes,
# not hours. Commits merge on their sha, so a later raise only adds the rest.
MAX_COMMIT_PAGES = 20


def setting(name: str) -> str | None:
    """A setting from .env, read again on every call, so a change needs no restart."""
    value = dotenv_values(ENV_FILE).get(name) if ENV_FILE.is_file() else None
    return value or os.environ.get(name) or None


def connected() -> bool:
    return bool(setting("GITHUB_USERNAME") and setting("GITHUB_TOKEN"))


class GitHub:
    origin = "github"

    def __init__(self, http, username: str, token: str):
        # http: requests, or dlt's requests helper, which retries on 429 and 5xx.
        self._http = http
        self.username = username
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, url: str, params=None):
        while True:
            response = self._http.get(url, params=params, headers=self._headers)
            # GitHub's rate limit answers 403 or 429 with the time it resets.
            if response.status_code in (403, 429) and response.headers.get("x-ratelimit-remaining") == "0":
                wait = int(response.headers.get("x-ratelimit-reset", time.time() + 60)) - time.time()
                time.sleep(min(max(wait, 1), 900))
                continue
            return response

    def get(self, path: str, **params) -> dict | list:
        response = self._get(f"{API_URL}{path}", params or None)
        response.raise_for_status()
        return response.json()

    def pages(self, path: str, max_pages: int | None = None, **params):
        """Every item of a paged list, following the Link header."""
        url, query, page = f"{API_URL}{path}", {"per_page": PAGE_SIZE, **params}, 0
        while url and (max_pages is None or page < max_pages):
            response = self._get(url, query)
            if response.status_code == 409:  # an empty repository has no commits to list
                return
            response.raise_for_status()
            yield from response.json()
            url, query, page = response.links.get("next", {}).get("url"), None, page + 1

    def graphql(self, query: str, **variables) -> dict:
        response = self._http.post(f"{API_URL}/graphql", json={"query": query, "variables": variables},
                                   headers=self._headers)
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise RuntimeError(f"GitHub GraphQL: {body['errors'][0].get('message')}")
        return body["data"]


def client(http):
    """The user's GitHub once connected, the sample until then."""
    if connected():
        return GitHub(http, setting("GITHUB_USERNAME"), setting("GITHUB_TOKEN"))
    from .sample import SampleGitHub

    return SampleGitHub()


# --- Rows ---------------------------------------------------------------------

# Every column of every table, so dlt creates a table even when an account has
# no rows for it (no commits yet, say), and a column even when it is empty in
# every row: dbt's staging models need both to exist.
TABLES = {
    "profile": {"login": "text", "name": "text", "bio": "text", "company": "text", "location": "text",
                "public_repos": "bigint", "followers": "bigint", "created_at": "timestamp", "origin": "text"},
    "repositories": {"repository_id": "bigint", "full_name": "text", "repository_name": "text",
                     "description": "text", "primary_language": "text", "topics": "text", "is_fork": "bool",
                     "is_private": "bool", "is_archived": "bool", "stars": "bigint", "forks": "bigint",
                     "homepage": "text", "html_url": "text", "created_at": "timestamp", "pushed_at": "timestamp",
                     "origin": "text"},
    "repository_languages": {"repository_id": "bigint", "language": "text", "bytes": "bigint", "origin": "text"},
    "commits": {"sha": "text", "repository_id": "bigint", "authored_at": "timestamp", "message_title": "text",
                "origin": "text"},
    "contribution_days": {"contribution_date": "date", "contributions": "bigint", "origin": "text"},
}



def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def profile_rows(gh) -> list[dict]:
    user = gh.get(f"/users/{gh.username}")
    return [{
        "login": user["login"],
        "name": user.get("name"),
        "bio": user.get("bio"),
        "company": user.get("company"),
        "location": user.get("location"),
        "public_repos": user.get("public_repos"),
        "followers": user.get("followers"),
        "created_at": _timestamp(user.get("created_at")),
        "origin": gh.origin,
    }]


def own_repositories(gh) -> list[dict]:
    """The user's own repositories, most recently pushed first; private ones too, for the token's owner."""
    return list(gh.pages("/user/repos", max_pages=1, affiliation="owner", sort="pushed"))


def repository_rows(gh, repos: list[dict]):
    for repo in repos:
        yield {
            "repository_id": repo["id"],
            "full_name": repo["full_name"],
            "repository_name": repo["name"],
            "description": repo.get("description"),
            "primary_language": repo.get("language"),
            "topics": ", ".join(repo.get("topics") or []) or None,
            "is_fork": repo.get("fork"),
            "is_private": repo.get("private"),
            "is_archived": repo.get("archived"),
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "homepage": repo.get("homepage") or None,
            "html_url": repo.get("html_url"),
            "created_at": _timestamp(repo.get("created_at")),
            "pushed_at": _timestamp(repo.get("pushed_at")),
            "origin": gh.origin,
        }


def language_rows(gh, repos: list[dict]):
    for repo in repos:
        if repo.get("fork"):
            continue  # a fork's languages are mostly someone else's code
        for language, size in gh.get(f"/repos/{repo['full_name']}/languages").items():
            yield {"repository_id": repo["id"], "language": language, "bytes": size, "origin": gh.origin}


def commit_rows(gh, repos: list[dict]):
    for repo in repos:
        if repo.get("fork"):
            continue
        commits = gh.pages(f"/repos/{repo['full_name']}/commits", max_pages=MAX_COMMIT_PAGES, author=gh.username)
        for commit in commits:
            author = (commit.get("commit") or {}).get("author") or {}
            message = (commit.get("commit") or {}).get("message") or ""
            yield {
                "sha": commit["sha"],
                "repository_id": repo["id"],
                # When it was written, in UTC; the committer date moves with rebases.
                "authored_at": _timestamp(author.get("date")),
                "message_title": message.splitlines()[0][:200] if message else None,
                "origin": gh.origin,
            }


CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def contribution_day_rows(gh, since: date, today: date):
    """One row per day, in years of at most 365 days: the most one query may span."""
    start = since
    while start <= today:
        end = min(start + timedelta(days=364), today)
        data = gh.graphql(
            CALENDAR_QUERY,
            login=gh.username,
            **{"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
        )
        calendar = data["user"]["contributionsCollection"]["contributionCalendar"]
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                yield {"contribution_date": date.fromisoformat(day["date"]),
                       "contributions": day["contributionCount"], "origin": gh.origin}
        start = end + timedelta(days=1)


def calendar_start(gh, today: date) -> date:
    """From the account's first day, at most ten years back."""
    created = profile_rows(gh)[0]["created_at"]
    first = created.date() if created else today - timedelta(days=365)
    return max(first, today - timedelta(days=3650))
