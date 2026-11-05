"""
The one-command installers (install.ps1, install.sh) and `datavloot start --run`.

The scripts are run end to end by hand on clean machines (#113); these tests
keep them parseable and in step with each other and with the toolkit.
"""

import json
import re
import shutil
import subprocess

import pytest

from datavloot_platform import cli

PS1 = cli.pathlib.Path(__file__).resolve().parent.parent / "install.ps1"
SH = PS1.with_name("install.sh")


def _setting(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, pattern
    return match.group(1)


# --------------------------------------------------------------------------
# the scripts
# --------------------------------------------------------------------------

def test_the_powershell_script_parses():
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("no PowerShell here")
    command = (
        "$errors = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{PS1}', [ref]$null, [ref]$errors); "
        "$errors | ForEach-Object { $_.ToString() }"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout


def test_the_shell_script_parses():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash here")
    result = subprocess.run([bash, "-n", str(SH)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_the_shell_script_has_unix_line_endings():
    """A CRLF checkout would make bash read `set -euo pipefail\\r` and stop."""
    assert b"\r\n" not in SH.read_bytes()


def test_the_powershell_script_is_ascii():
    """Windows PowerShell 5.1 reads a script without a BOM in the ANSI code page."""
    PS1.read_bytes().decode("ascii")


def test_both_scripts_install_the_same_things():
    ps1, sh = PS1.read_text(encoding="utf-8"), SH.read_text(encoding="utf-8")
    assert _setting(ps1, r"^\$PythonVersion = '([\d.]+)'") == _setting(sh, r"^PYTHON_VERSION=([\d.]+)")
    assert _setting(ps1, r"^\$CrowsNestPort = (\d+)") == _setting(sh, r"^CROWSNEST_PORT=(\d+)")
    assert _setting(ps1, r"^\$DagsterPort = (\d+)") == _setting(sh, r"^DAGSTER_PORT=(\d+)")
    for text in (ps1, sh):
        assert "datavloot[optimist]@latest" in text
        assert "datavloot start" in text and "--run" in text
        for variable in ("DATAVLOOT_DIR", "DATAVLOOT_VERSION", "DATAVLOOT_FROM"):
            assert variable in text


def test_the_python_version_is_one_the_demo_accepts():
    version = _setting(SH.read_text(encoding="utf-8"), r"^PYTHON_VERSION=([\d.]+)")
    demo = (cli.TEMPLATES_DIR / "demo" / "pyproject.toml").read_text(encoding="utf-8")
    low, high = re.search(r'requires-python = ">=([\d.]+),<([\d.]+)"', demo).groups()
    as_tuple = lambda v: tuple(int(p) for p in v.split("."))  # noqa: E731
    assert as_tuple(low) <= as_tuple(version) < as_tuple(high)


def test_the_crows_nest_port_is_the_cli_default():
    port = int(_setting(SH.read_text(encoding="utf-8"), r"^CROWSNEST_PORT=(\d+)"))
    parser_source = cli.pathlib.Path(cli.__file__).read_text(encoding="utf-8")
    assert f'"--port", type=int, default={port}' in parser_source


# --------------------------------------------------------------------------
# datavloot start --run
# --------------------------------------------------------------------------

def _asset(path, materializable=True, partitioned=False, job="__ASSET_JOB"):
    return {
        "assetKey": {"path": path},
        "isMaterializable": materializable,
        "isPartitioned": partitioned,
        "jobNames": [job, "lake_maintenance"],
    }


@pytest.fixture
def dagster(monkeypatch):
    """A stand-in for Dagster's GraphQL API; returns the requests it received."""
    httpx = pytest.importorskip("httpx")
    state = {"assets": [], "launch": {"__typename": "LaunchRunSuccess", "run": {"runId": "r1"}},
             "requests": []}

    def handler(request):
        body = json.loads(request.content)
        state["requests"].append(body)
        if "launchRun" in body["query"]:
            return httpx.Response(200, json={"data": {"launchRun": state["launch"]}})
        return httpx.Response(200, json={"data": {"repositoriesOrError": {
            "__typename": "RepositoryConnection",
            "nodes": [{"name": "__repository__", "location": {"name": "noaa"},
                       "assetNodes": state["assets"]}],
        }}})

    transport = httpx.MockTransport(handler)

    def post(url, **kwargs):
        kwargs.pop("timeout", None)
        with httpx.Client(transport=transport) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", post)
    return state


def test_run_starts_every_materializable_asset_in_one_run(dagster):
    dagster["assets"] = [
        _asset(["noaa", "guam_2025"]),
        _asset(["stg_noaa__guam_2025"]),
        _asset(["raw_source"], materializable=False),
    ]
    message = cli._materialize_all("http://dagster/graphql")
    assert message.startswith("Started a run of 2 assets in noaa"), message

    launch = dagster["requests"][-1]["variables"]["params"]
    assert launch["selector"] == {
        "repositoryLocationName": "noaa",
        "repositoryName": "__repository__",
        "pipelineName": "__ASSET_JOB",
        "assetSelection": [{"path": ["noaa", "guam_2025"]}, {"path": ["stg_noaa__guam_2025"]}],
    }


def test_run_leaves_partitioned_assets_out_and_says_so(dagster):
    dagster["assets"] = [_asset(["a"]), _asset(["daily"], partitioned=True, job="__ASSET_JOB_0")]
    message = cli._materialize_all("http://dagster/graphql")
    assert "1 partitioned assets left out" in message
    assert dagster["requests"][-1]["variables"]["params"]["selector"]["assetSelection"] == [
        {"path": ["a"]}
    ]


def test_a_refused_run_is_reported_with_the_manual_route(dagster):
    dagster["assets"] = [_asset(["a"])]
    dagster["launch"] = {"__typename": "PythonError", "message": "boom"}
    message = cli._materialize_all("http://dagster/graphql")
    assert "Could not start the run: boom" in message
    assert "Materialize all" in message


def test_no_assets_starts_nothing(dagster):
    message = cli._materialize_all("http://dagster/graphql")
    assert "Found no assets" in message
    assert not any("launchRun" in r["query"] for r in dagster["requests"])


def test_an_unreachable_dagster_does_not_raise():
    message = cli._materialize_all("http://127.0.0.1:9/graphql")
    assert "Could not start the run" in message
