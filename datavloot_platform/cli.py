import argparse
import importlib.metadata
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

from datavloot_platform import location
from datavloot_platform.crowsnest.processes import terminate_tree

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

# The optimist dbt package release that new projects get, the one this toolkit
# release was tested with: a tag of github.com/datavloot/dbt-datavloot-optimist.
# It has its own version series, apart from the toolkit's: bump it with every
# release of that repository.
DBT_PACKAGE_VERSION = "0.1.1"

_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".venv", "target", "dbt_packages", "logs"
)


def _copy_template(source: pathlib.Path, dest: pathlib.Path) -> None:
    if dest.exists():
        sys.exit(f"Error: '{dest}' already exists. Choose a different path.")
    shutil.copytree(source, dest, ignore=_IGNORE)


def _preinstall_extensions(dest: pathlib.Path) -> None:
    """
    Install the DuckDB extensions now, while the user is here to read a failure,
    then create the project's empty lake so readers find one before the first run.

    Best effort: a failed download prints the manual route and the project is
    still created; the lake is then created by whatever attaches it first.
    Without the optimist extra there is no duckdb to install into, and nothing
    that would load an extension either.
    """
    try:
        import duckdb
    except ImportError:
        return

    from datavloot_platform import extensions, storage

    print(f"Installing DuckDB extensions ({', '.join(extensions.REQUIRED)})…", flush=True)
    conn = duckdb.connect()
    try:
        failures = extensions.install(conn)
    finally:
        conn.close()
    for message in failures:
        print(f"Warning: {message}\n", file=sys.stderr)
    if not failures:
        storage.create(dest)


def _warn_about_location(path: pathlib.Path, project_name: str) -> None:
    """Print warnings about where the project and this environment live; never stop."""
    warnings = location.project_warnings(path, project_name) + location.environment_warnings()
    for warning in warnings:
        print(f"Warning: {warning}\n", file=sys.stderr)


def _to_identifier(name: str) -> str:
    """Convert a directory name to a valid Python identifier."""
    return name.replace("-", "_").replace(" ", "_").lower()


def _substitute(dest: pathlib.Path, project_name: str) -> None:
    """Replace placeholder tokens in the copied scaffold with the project name."""
    module_name = f"{project_name}_platform"

    # Rename the placeholder directory before touching file contents
    placeholder_dir = dest / "project_platform"
    if placeholder_dir.exists():
        placeholder_dir.rename(dest / module_name)

    # Ordered substitutions: more specific tokens first to avoid partial matches
    substitutions = [
        ("project_dbt_assets", f"{project_name}_dbt_assets"),
        ("project_dbt_project", f"{project_name}_dbt_project"),
        ("project_platform", module_name),
        ("<project_name>", project_name),
    ]

    for fpath in dest.rglob("*"):
        if not fpath.is_file():
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        new_content = content
        for old, new in substitutions:
            new_content = new_content.replace(old, new)
        if new_content != content:
            fpath.write_text(new_content, encoding="utf-8")


def _versions() -> dict[str, str]:
    """
    The versions a new project pins, by placeholder.

    Read before a template is copied, so a failure here leaves no half-made
    project behind.
    """
    return {
        "<toolkit_version>": importlib.metadata.version("datavloot"),
        "<dbt_package_version>": DBT_PACKAGE_VERSION,
    }


def _pin_versions(dest: pathlib.Path, versions: dict[str, str]) -> None:
    """
    Pin the toolkit and the dbt package in a new project to known versions.

    The toolkit to this release and its later patches (`~=`), the dbt package to
    the exact release this toolkit was tested with. A patch of the toolkit can
    therefore run with the dbt package of the release that created the project;
    moving that pin is left to the user, or to `datavloot upgrade` (#55).
    """
    for name in ("pyproject.toml", "packages.yml"):
        path = dest / name
        text = path.read_text(encoding="utf-8")
        for placeholder, version in versions.items():
            text = text.replace(placeholder, version)
        path.write_text(text, encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> None:
    dest = pathlib.Path(args.path).resolve()
    project_name = _to_identifier(dest.name)
    versions = _versions()

    _copy_template(TEMPLATES_DIR / "scaffold", dest)
    _substitute(dest, project_name)
    _pin_versions(dest, versions)
    _preinstall_extensions(dest)

    _warn_about_location(dest, project_name)
    print(f"Project '{project_name}' created at '{dest}'.\n")
    print("Next steps:")
    print(f"  1. cd {dest}")
    print(f"  2. pip install -e .   # install the project's Python package")
    print(f"  3. dbt deps           # install the optimist dbt package")
    print(f"  4. dbt parse          # compile the manifest for Dagster")
    print(f"  5. datavloot start    # Dagster at http://localhost:3000, the Crows Nest at http://localhost:8080")
    print(f"\nSee data-instructions.md or hand it to your AI assistant at the start of a session so it")
    print(f"knows the toolkit's conventions, then start adding your data sources.")


def cmd_demo(args: argparse.Namespace) -> None:
    dest = (
        pathlib.Path(args.path).resolve()
        if args.path
        else pathlib.Path.cwd() / "optimist-demo"
    )
    versions = _versions()
    _copy_template(TEMPLATES_DIR / "demo", dest)
    _pin_versions(dest, versions)
    _preinstall_extensions(dest)
    # The demo keeps its own name (noaa), unlike a scaffolded project.
    _warn_about_location(dest, "noaa")
    print(f"NOAA demo project created at '{dest}'.\n")
    print("Next steps:")
    print(f"  1. cd {dest}")
    print(f"  2. pip install -e .   # install the demo's Python package")
    print(f"  3. dbt deps           # install the optimist dbt package")
    print(f"  4. dbt parse          # compile the manifest for Dagster")
    print(f"  5. datavloot start    # Dagster at http://localhost:3000, the Crows Nest at http://localhost:8080")
    print(f"\nThe first run downloads NOAA's Guam 2025 AIS data into data/ (41 MB, 366 MB unpacked).")
    print(f"\nHand data-instructions.md to your AI assistant at the start of a session so it")
    print(f"knows the toolkit's conventions.")


def cmd_crowsnest(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        sys.exit(
            "Error: uvicorn is required for the Crows Nest. "
            "Install it with: pip install datavloot[optimist]"
        )

    from datavloot_platform.crowsnest.config import get_config
    from datavloot_platform.crowsnest.server import create_app

    config = get_config()
    print(f"Starting Crows Nest on http://{args.host}:{args.port}")
    if config.ducklake_catalog_path:
        print(f"  Lake:    {config.ducklake_catalog_path} (as {config.ducklake_alias})")
    else:
        print(f"  DuckDB:  {config.duckdb_path}")
    print(f"  Dagster: {config.dagster_graphql_url}")
    print(f"  Marimo:  {config.marimo_url}")
    from datavloot_platform.crowsnest.auth import get_auth_token
    print(f"  Auth:    {'token required' if get_auth_token() else 'none (set CROWSNEST_AUTH_TOKEN to require one)'}")
    print()

    if args.open:
        import threading
        import webbrowser
        url = f"http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.port}"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app = create_app()
    # The Marimo servers run in a session of their own, and the atexit hooks
    # that stop them run only when Python exits normally. uvicorn shuts down on
    # SIGTERM and then raises it again into the handler it found, so make that
    # one exit normally. Closing the terminal sends SIGHUP, which uvicorn does
    # not handle: turn it into that SIGTERM, unless SIGHUP is ignored (nohup).
    if signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if hasattr(signal, "SIGHUP") and signal.getsignal(signal.SIGHUP) is signal.SIG_DFL:
        signal.signal(signal.SIGHUP, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
    uvicorn.run(app, host=args.host, port=args.port)


# GraphQL probe: is the webserver up, and did every code location load?
# A webserver that answers while its code location is broken is the failure mode that
# matters -- the UI responds, but no assets exist, so a plain "did it respond" check
# passes on a platform that cannot actually run anything.
_READINESS_QUERY = """
{
  workspaceOrError {
    __typename
    ... on Workspace {
      locationEntries {
        name
        loadStatus
        locationOrLoadError {
          __typename
          ... on PythonError { message }
        }
      }
    }
    ... on PythonError { message }
  }
}
"""


def _wait_for_dagster(proc: subprocess.Popen, graphql_url: str, timeout: int = 60):
    """
    Block until Dagster is genuinely usable.  Return None on success, else an error string.

    Four outcomes are distinguished, because they warrant different responses:
      - process died          -> fail at once; waiting out the timeout tells us nothing
      - webserver not up yet  -> keep polling
      - locations still load  -> keep polling
      - a location failed     -> fail, surfacing the Python error Dagster reported
    """
    import httpx

    last_detail = "no response from the webserver"

    for _ in range(timeout):
        if proc.poll() is not None:
            return f"Dagster exited with code {proc.returncode} before becoming ready."

        time.sleep(1)
        try:
            resp = httpx.post(graphql_url, json={"query": _READINESS_QUERY}, timeout=2)
        except Exception:
            continue  # not listening yet

        if resp.status_code != 200:
            last_detail = f"webserver returned HTTP {resp.status_code}"
            continue

        try:
            workspace = resp.json()["data"]["workspaceOrError"]
        except Exception:
            last_detail = "webserver returned an unreadable GraphQL response"
            continue

        if workspace.get("__typename") == "PythonError":
            message = (workspace.get("message") or "").rstrip()
            return f"Dagster failed to load the workspace:\n\n{message}"

        entries = workspace.get("locationEntries", [])
        if not entries:
            last_detail = "no code locations found in the workspace"
            continue

        loading = [e.get("name", "?") for e in entries if e.get("loadStatus") == "LOADING"]
        if loading:
            last_detail = f"code location(s) still loading: {', '.join(loading)}"
            continue

        failed = [
            e for e in entries
            if (e.get("locationOrLoadError") or {}).get("__typename") == "PythonError"
        ]
        if failed:
            details = "\n\n".join(
                "  Code location '{}' failed to load:\n{}".format(
                    e.get("name", "?"),
                    ((e.get("locationOrLoadError") or {}).get("message") or "").rstrip(),
                )
                for e in failed
            )
            return f"Dagster started but its code location(s) did not load.\n\n{details}"

        return None

    return f"Dagster did not become ready within {timeout} seconds ({last_detail})."


def cmd_start(args: argparse.Namespace) -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        sys.exit(
            "Error: uvicorn is required. "
            "Install it with: pip install datavloot[optimist]"
        )

    from datavloot_platform.crowsnest.config import get_config

    graphql_url = get_config().dagster_graphql_url

    # `start` runs from the project directory, which may have been created or
    # moved without going through `new`.
    project_dir = pathlib.Path.cwd()
    _warn_about_location(project_dir, _to_identifier(project_dir.name))

    print("Starting Dagster…")
    # POSIX: own session, so the whole tree can be signalled as one group.
    dagster_proc = subprocess.Popen(
        ["dagster", "dev"],
        start_new_session=(os.name != "nt"),
    )

    print(f"Waiting for Dagster to be ready at {graphql_url}…", flush=True)
    error = _wait_for_dagster(dagster_proc, graphql_url)
    if error:
        terminate_tree(dagster_proc)
        sys.exit(f"Error: {error}")

    print("Dagster is ready.")

    try:
        cmd_crowsnest(args)
    finally:
        # A closed terminal takes stdout with it, and Dagster has to stop anyway.
        try:
            print("\nShutting down Dagster…")
        except OSError:
            pass
        terminate_tree(dagster_proc)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="datavloot",
        description="Datavloot CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser(
        "new", help="Scaffold a new project at the given path"
    )
    new_parser.add_argument("path", help="Path where the project will be created")
    new_parser.set_defaults(func=cmd_new)

    demo_parser = subparsers.add_parser(
        "demo", help="Copy the NOAA worked example to a local directory"
    )
    demo_parser.add_argument(
        "path",
        nargs="?",
        help="Path for the demo (default: ./optimist-demo)",
    )
    demo_parser.set_defaults(func=cmd_demo)

    crowsnest_parser = subparsers.add_parser(
        "launch", help="Start the Crows Nest unified dashboard"
    )
    crowsnest_parser.add_argument(
        "--port", type=int, default=8080, help="Port to listen on (default: 8080)"
    )
    crowsnest_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    crowsnest_parser.add_argument(
        "--no-open", dest="open", action="store_false",
        help="Do not open the browser automatically"
    )
    crowsnest_parser.set_defaults(func=cmd_crowsnest, open=True)

    start_parser = subparsers.add_parser(
        "start", help="Start Dagster and the Crows Nest together"
    )
    start_parser.add_argument(
        "--port", type=int, default=8080, help="Crows Nest port (default: 8080)"
    )
    start_parser.add_argument(
        "--host", default="127.0.0.1", help="Crows Nest host (default: 127.0.0.1)"
    )
    start_parser.add_argument(
        "--no-open", dest="open", action="store_false",
        help="Do not open the browser automatically"
    )
    start_parser.set_defaults(func=cmd_start, open=True)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
