"""
Shared fixtures for the toolkit's own tests.

These test the *templates and packaging*, not a user's project. The scaffold
fixture goes through the same two calls `cli.cmd_new` makes, so a change to
either one is covered.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

from datavloot_platform import cli

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    return REPO_ROOT


def _scaffold(dest: pathlib.Path, name: str) -> pathlib.Path:
    """Create a project exactly as `datavloot new <dest>` does."""
    cli._copy_template(cli.TEMPLATES_DIR / "scaffold", dest)
    cli._substitute(dest, cli._to_identifier(name))
    return dest


@pytest.fixture
def scaffold(tmp_path: pathlib.Path) -> pathlib.Path:
    """A freshly scaffolded project named 'probe'. No dbt commands run."""
    return _scaffold(tmp_path / "probe", "probe")


def use_local_optimist(project: pathlib.Path) -> None:
    """
    Point the project's packages.yml at this checkout instead of the published
    revision.

    Without this the smoke test installs `revision: 0.1.x` from GitLab, so it
    would validate the last release rather than the branch under review -- a
    change to dbt/optimist would pass CI while being broken.
    """
    local_pkg = (REPO_ROOT / "dbt" / "optimist").as_posix()
    (project / "packages.yml").write_text(
        "packages:\n"
        f"  - local: \"{local_pkg}\"\n"
        "  - package: dbt-labs/dbt_utils\n"
        "    version: [\">=1.4.0\", \"<2.0.0\"]\n"
        "  - package: elementary-data/elementary\n"
        "    version: [\">=0.25.0\", \"<0.26.0\"]\n",
        encoding="utf-8",
    )


def run_dbt(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess:
    """
    Run dbt in `cwd` with that directory as the profiles dir.

    Returns the completed process rather than raising, so a test can assert on
    stdout as well as the exit code.
    """
    env = {**os.environ, "DBT_PROFILES_DIR": str(cwd), "NO_COLOR": "1"}
    return subprocess.run(
        [shutil.which("dbt") or "dbt", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
