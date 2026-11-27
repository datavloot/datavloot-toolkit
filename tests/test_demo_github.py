"""
The GitHub demo's own code, without GitHub: the client against a fake HTTP
layer, and the sample developer that stands in for an account.
"""

import importlib
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from .conftest import _demo


@pytest.fixture
def platform(tmp_path, monkeypatch):
    project = _demo(tmp_path / "github", "github")
    monkeypatch.syspath_prepend(str(project))
    for name in [m for m in sys.modules if m.startswith("github_platform")]:
        monkeypatch.delitem(sys.modules, name)
    for name in ("GITHUB_USERNAME", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return importlib.import_module("github_platform.github"), importlib.import_module("github_platform.sample")


class _Response:
    def __init__(self, body, status=200, links=None, headers=None):
        self._body, self.status_code = body, status
        self.links, self.headers = links or {}, headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_no_token_means_the_sample(platform):
    github, sample = platform
    assert not github.connected()
    assert isinstance(github.client(http=None), sample.SampleGitHub)


def test_pages_follow_the_link_header_and_skip_empty_repositories(platform):
    github, _ = platform
    first, second = f"{github.API_URL}/repos/me/a/commits", f"{github.API_URL}/repos/me/a/commits?page=2"
    answers = {
        first: _Response([{"sha": "1"}], links={"next": {"url": second}}),
        second: _Response([{"sha": "2"}]),
        f"{github.API_URL}/repos/me/empty/commits": _Response({"message": "Git Repository is empty."}, 409),
    }

    class Http:
        def get(self, url, params=None, headers=None):
            return answers[url]

    gh = github.GitHub(Http(), "me", "tok")
    assert [c["sha"] for c in gh.pages("/repos/me/a/commits")] == ["1", "2"]
    assert list(gh.pages("/repos/me/empty/commits")) == []


def test_forks_are_listed_but_their_code_is_not_counted(platform):
    github, sample = platform
    gh = sample.SampleGitHub()
    repos = github.own_repositories(gh)
    forks = {r["id"] for r in repos if r["fork"]}
    assert forks, "the sample should show a fork"
    assert forks <= {r["repository_id"] for r in github.repository_rows(gh, repos)}
    assert not forks & {r["repository_id"] for r in github.language_rows(gh, repos)}
    assert not forks & {r["repository_id"] for r in github.commit_rows(gh, repos)}


def test_the_calendar_has_every_day_once(platform):
    github, sample = platform
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    gh = sample.SampleGitHub(now)
    today = now.date()
    days = [r["contribution_date"] for r in github.contribution_day_rows(gh, github.calendar_start(gh, today), today)]
    assert days == sorted(set(days)), "a day twice, or out of order, across the yearly queries"
    assert days[-1] == today and (days[-1] - days[0]).days + 1 == len(days)


def test_the_sample_is_the_same_every_run(platform):
    github, sample = platform
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    rows = lambda: list(github.commit_rows(sample.SampleGitHub(now), github.own_repositories(sample.SampleGitHub(now))))  # noqa: E731
    first = rows()
    assert first == rows()
    assert max(r["authored_at"] for r in first) <= now
    assert len({r["sha"] for r in first}) == len(first), "sha is the merge key"


def test_every_row_has_exactly_the_declared_columns(platform):
    """assets.py creates each table from github.TABLES, also an empty one; a column missing there would be dropped."""
    github, sample = platform
    gh = sample.SampleGitHub()
    repos, today = github.own_repositories(gh), date.today()
    tables = {
        "profile": github.profile_rows(gh), "repositories": github.repository_rows(gh, repos),
        "repository_languages": github.language_rows(gh, repos), "commits": github.commit_rows(gh, repos),
        "contribution_days": github.contribution_day_rows(gh, today - timedelta(days=3), today),
    }
    assert set(tables) == set(github.TABLES)
    for table, rows in tables.items():
        assert set(next(iter(rows))) == set(github.TABLES[table]), table
