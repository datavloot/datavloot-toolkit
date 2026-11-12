"""
The one-command installers in installers/ and `datavloot start --run`.

Three scripts, each for PowerShell and for bash: install-demo (the NOAA demo),
new-project (a new, empty project) and install-project (a project from its
repository). They are run end to end by hand on clean machines (#113); these
tests keep them parseable and in step with each other and with the toolkit.
"""

import json
import re
import shutil
import subprocess

import pytest

from datavloot_platform import cli

INSTALLERS = cli.pathlib.Path(__file__).resolve().parent.parent / "installers"
NAMES = ("install-demo", "new-project", "install-project")
PS1 = {name: INSTALLERS / f"{name}.ps1" for name in NAMES}
SH = {name: INSTALLERS / f"{name}.sh" for name in NAMES}
ALL = [*PS1.values(), *SH.values()]
NAME_PATTERN = "^[A-Za-z][A-Za-z0-9_-]*$"


def _setting(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, pattern
    return match.group(1)


def _text(path) -> str:
    return path.read_text(encoding="utf-8")


def _shared(path) -> str:
    """The part every script of one shell repeats, between its two markers."""
    text = _text(path)
    return text[text.index("# --- Shared by"):text.index("# --- End of the shared part")]


# --------------------------------------------------------------------------
# the scripts
# --------------------------------------------------------------------------

def test_there_are_exactly_these_scripts():
    """The release uploads installers/*; a stray file would land on the release."""
    assert sorted(p.name for p in INSTALLERS.iterdir()) == sorted(p.name for p in ALL)


@pytest.mark.parametrize("script", PS1.values(), ids=lambda p: p.name)
def test_the_powershell_scripts_parse(script):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("no PowerShell here")
    command = (
        "$errors = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors); "
        "$errors | ForEach-Object { $_.ToString() }"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", result.stdout


@pytest.mark.parametrize("script", SH.values(), ids=lambda p: p.name)
def test_the_shell_scripts_parse(script):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash here")
    result = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SH.values(), ids=lambda p: p.name)
def test_the_shell_scripts_have_unix_line_endings(script):
    """A CRLF checkout would make bash read `set -euo pipefail\\r` and stop."""
    assert b"\r\n" not in script.read_bytes()


@pytest.mark.parametrize("script", ALL, ids=lambda p: p.name)
def test_the_scripts_are_ascii(script):
    """Windows PowerShell 5.1 reads a script without a BOM in the ANSI code page."""
    script.read_bytes().decode("ascii")


@pytest.mark.parametrize("scripts", [PS1, SH], ids=["ps1", "sh"])
def test_the_shared_part_is_the_same_in_every_script(scripts):
    """Each script is served on its own, so the helpers are copied: keep the copies equal."""
    demo = _shared(scripts["install-demo"])
    for name in ("new-project", "install-project"):
        assert _shared(scripts[name]) == demo, f"{name}: copy the shared part from install-demo"


def test_powershell_and_bash_install_the_same_things():
    ps1, sh = _text(PS1["install-demo"]), _text(SH["install-demo"])
    assert _setting(ps1, r"^\$PythonVersion = '([\d.]+)'") == _setting(sh, r"^PYTHON_VERSION=([\d.]+)")
    assert _setting(ps1, r"^\$CrowsNestPort = (\d+)") == _setting(sh, r"^CROWSNEST_PORT=(\d+)")
    assert _setting(ps1, r"^\$DagsterPort = (\d+)") == _setting(sh, r"^DAGSTER_PORT=(\d+)")
    for text in (ps1, sh):
        assert "datavloot[optimist]@latest" in text
        for variable in ("DATAVLOOT_DIR", "DATAVLOOT_VERSION", "DATAVLOOT_FROM"):
            assert variable in text


@pytest.mark.parametrize("scripts", [PS1, SH], ids=["ps1", "sh"])
def test_each_script_does_its_own_thing(scripts):
    demo, new, project = (_text(scripts[name]) for name in NAMES)
    # The demo, and only the demo, starts a run straight away: it fetches its own data.
    assert "datavloot demo" in demo and "start --run" in demo
    assert "DATAVLOOT_PROJECT" not in demo
    # A new, empty project from `datavloot new`, under a name the script asks for.
    assert "datavloot new $dir" in new or 'datavloot new "$dir"' in new
    assert "Name of the new project" in new and NAME_PATTERN in new
    assert "start --run" not in new and "DATAVLOOT_PROJECT" not in new
    # A project from its repository, through `datavloot new --from` with its options.
    for variable in ("DATAVLOOT_PROJECT", "DATAVLOOT_REF", "DATAVLOOT_PATH"):
        assert variable in project
    assert "--ref" in project and "--path" in project
    assert "start --run" not in project


@pytest.mark.parametrize("name", ["new-project", "install-project"])
def test_the_shell_scripts_ask_their_questions_on_the_terminal(name):
    """Under curl | bash, stdin is the script: reading it would eat the rest."""
    assert re.search(r"\bread\b[^\n]*</dev/tty", _text(SH[name]))


@pytest.mark.parametrize("url, name", [
    ("https://gitlab.com/datavloot/ketenconnect-demo", "ketenconnect-demo"),
    ("https://gitlab.com/datavloot/ketenconnect-demo.git", "ketenconnect-demo"),
    ("https://gitlab.com/datavloot/ketenconnect-demo/-/tree/main", "ketenconnect-demo"),
    ("https://github.com/owner/repo/", "repo"),
])
def test_the_default_folder_is_named_after_the_repository(url, name):
    """The same name in both scripts, by running each one's own expression."""
    bash = shutil.which("bash")
    if bash:
        lines = [l.strip() for l in _text(SH["install-project"]).splitlines()
                 if l.strip().startswith('default_name="${')]
        assert lines
        script = f'project="{url}"\n' + "\n".join(lines) + '\nprintf %s "$default_name"'
        out = subprocess.run([bash, "-c", script], capture_output=True, text=True, timeout=30)
        assert out.stdout == name, out.stderr
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell:
        line = next(l.strip() for l in _text(PS1["install-project"]).splitlines()
                    if l.strip().startswith("$defaultName = ((("))
        out = subprocess.run(
            [shell, "-NoProfile", "-Command", f"$project = '{url}'; {line}; $defaultName"],
            capture_output=True, text=True, timeout=60,
        )
        assert out.stdout.strip() == name, out.stderr
    if not bash and not shell:
        pytest.skip("neither bash nor PowerShell here")


@pytest.mark.parametrize("name, valid", [
    ("harbor", True), ("my-project", True), ("shop_2", True),
    ("2shop", False), ("my project", False), ("../x", False), ("", False),
])
def test_the_project_name_pattern(name, valid):
    """The name becomes a Python package and a dbt project; both scripts check it with NAME_PATTERN."""
    assert bool(re.fullmatch(NAME_PATTERN, name)) is valid


def test_new_leaves_the_next_steps_to_the_script(tmp_path, monkeypatch, capsys):
    """Under new-project.*, `datavloot new` does not print the pip steps the script replaces."""
    monkeypatch.setattr(cli, "_preinstall_extensions", lambda dest: None)
    monkeypatch.setenv("DATAVLOOT_INSTALLER", "1")
    args = cli.argparse.Namespace(path=str(tmp_path / "harbor"), source=None, ref=None, subdir=None)
    cli.cmd_new(args)
    out = capsys.readouterr().out
    assert "created at" in out and "Next steps" not in out
    assert (tmp_path / "harbor" / "dbt_project.yml").is_file()


def test_the_python_version_is_one_the_demo_accepts():
    version = _setting(_text(SH["install-demo"]), r"^PYTHON_VERSION=([\d.]+)")
    demo = (cli.TEMPLATES_DIR / "demo" / "pyproject.toml").read_text(encoding="utf-8")
    low, high = re.search(r'requires-python = ">=([\d.]+),<([\d.]+)"', demo).groups()
    as_tuple = lambda v: tuple(int(p) for p in v.split("."))  # noqa: E731
    assert as_tuple(low) <= as_tuple(version) < as_tuple(high)


def test_the_crows_nest_port_is_the_cli_default():
    port = int(_setting(_text(SH["install-demo"]), r"^CROWSNEST_PORT=(\d+)"))
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
    pytest.importorskip("httpx")
    message = cli._materialize_all("http://127.0.0.1:9/graphql")
    assert "Could not start the run" in message
