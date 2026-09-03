"""
What the built wheel is allowed to contain.

The 0.1.1 wheel published to PyPI was 276 MB unpacked, 5,652 files, of which
over 99% was frontend build input no user executes. The cause is one rule:
hatchling honours the *root* .gitignore and ignores nested ones, so everything
hidden by crowsnest/frontend/.gitignore and templates/demo/.gitignore ships.

A hand-maintained exclude list fixes today's directories and goes stale the next
time someone adds a nested ignore file, so this asserts on the built artifact
instead.
"""

import pathlib
import re
import shutil
import subprocess
import zipfile

import pytest

# Building a wheel walks the whole tree; keep it out of the fast suite.
pytestmark = pytest.mark.package

# Build inputs and generated state. None of this belongs in a wheel.
FORBIDDEN = re.compile(
    r"(^|/)(node_modules|\.next|out|dbt_packages|target|logs|__pycache__)/|\.duckdb$"
)

# The 0.1.1 wheel was 276 MB unpacked. The source, templates and pre-built
# static bundle together are a few MB; 25 leaves generous headroom while still
# catching a return of the build inputs by two orders of magnitude.
MAX_UNPACKED_MB = 25


# Where build inputs accumulate on a developer machine. Each is hidden by a
# *nested* .gitignore, so none exists in a fresh clone -- which is exactly why
# this fixture has to plant them.
#
# A fresh CI clone contains none of these directories, so building there produces
# a small wheel no matter what pyproject.toml says: the test would pass while the
# bug is fully intact. The 0.1.1 wheel that shipped 276 MB to PyPI was built on a
# developer machine, where they all exist.
#
# Every location is covered by a nested .gitignore, so the decoys stay invisible
# to git even if cleanup is skipped, and real directories are never removed.
DECOY_DIRS = [
    "datavloot_platform/crowsnest/frontend/node_modules",
    "datavloot_platform/crowsnest/frontend/.next",
    "datavloot_platform/crowsnest/frontend/out",
    "datavloot_platform/templates/demo/dbt_packages",
    "datavloot_platform/templates/demo/target",
]

DECOY_NAME = "__packaging_test_decoy__.txt"


@pytest.fixture(scope="module")
def wheel(tmp_path_factory, repo_root: pathlib.Path) -> pathlib.Path:
    """Build a wheel with build inputs present, as on a developer machine."""
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")

    made_files: list[pathlib.Path] = []
    made_dirs: list[pathlib.Path] = []
    try:
        for rel in DECOY_DIRS:
            d = repo_root / rel
            if not d.exists():
                d.mkdir(parents=True)
                made_dirs.append(d)
            decoy = d / DECOY_NAME
            if not decoy.exists():
                decoy.write_text("planted by tests/test_packaging.py", encoding="utf-8")
                made_files.append(decoy)

        out = tmp_path_factory.mktemp("dist")
        proc = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(out)],
            cwd=repo_root, capture_output=True, text=True, timeout=1800,
        )
        assert proc.returncode == 0, "uv build failed:" + proc.stderr[-3000:]

        wheels = list(out.glob("*.whl"))
        assert len(wheels) == 1, "expected one wheel, got %s" % wheels
        return wheels[0]
    finally:
        for f in made_files:
            f.unlink(missing_ok=True)
        for d in reversed(made_dirs):
            try:
                d.rmdir()          # only ever removes a directory this fixture created
            except OSError:
                pass


def test_wheel_excludes_build_inputs(wheel: pathlib.Path):
    """No build input, dependency tree, or generated database ships."""
    with zipfile.ZipFile(wheel) as z:
        offenders = sorted({
            "/".join(n.split("/")[:4]) for n in z.namelist() if FORBIDDEN.search(n)
        })

    assert offenders == [], (
        "the wheel ships build inputs:\n  "
        + "\n  ".join(offenders)
        + "\n\nAdd them to [tool.hatch.build.targets.wheel] exclude in pyproject.toml. "
          "Hatchling does not honour nested .gitignore files, so each one must be listed."
    )


def test_wheel_is_not_enormous(wheel: pathlib.Path):
    """Total unpacked size stays within an order of magnitude of the real payload."""
    with zipfile.ZipFile(wheel) as z:
        unpacked_mb = sum(i.file_size for i in z.infolist()) / 1e6
        count = len(z.namelist())

    assert unpacked_mb < MAX_UNPACKED_MB, (
        f"wheel unpacks to {unpacked_mb:,.1f} MB across {count:,} files "
        f"(ceiling {MAX_UNPACKED_MB} MB)"
    )


def test_the_served_frontend_bundle_is_present(wheel: pathlib.Path):
    """
    Excluding build inputs must not exclude what the server actually serves.

    crowsnest/server.py mounts crowsnest/static/. If an exclude rule ever
    swallows it, the Crows Nest serves nothing and this is the test that says so.
    """
    with zipfile.ZipFile(wheel) as z:
        static = [n for n in z.namelist() if "/crowsnest/static/" in n]

    assert static, "crowsnest/static/ is missing; the Crows Nest would serve nothing"
    assert any(n.endswith(".html") for n in static), "no HTML in crowsnest/static/"


def test_templates_ship(wheel: pathlib.Path):
    """`datavloot new` and `datavloot demo` copy these out of the installed package."""
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()

    for required in (
        "datavloot_platform/templates/scaffold/dbt_project.yml",
        "datavloot_platform/templates/scaffold/profiles.yml",
        "datavloot_platform/templates/demo/dbt_project.yml",
    ):
        assert required in names, f"{required} is missing from the wheel"


def test_license_is_declared(wheel: pathlib.Path):
    """Apache-2.0 must reach PyPI, not just sit in the repository."""
    with zipfile.ZipFile(wheel) as z:
        meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
        text = z.read(meta).decode("utf-8", "replace")

    assert "Apache-2.0" in text, "no licence in wheel metadata; PyPI will show none"
