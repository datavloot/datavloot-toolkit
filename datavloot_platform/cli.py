import argparse
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"

_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".venv", "target", "dbt_packages", "logs"
)


def _copy_template(source: pathlib.Path, dest: pathlib.Path) -> None:
    if dest.exists():
        sys.exit(f"Error: '{dest}' already exists. Choose a different path.")
    shutil.copytree(source, dest, ignore=_IGNORE)


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


def cmd_new(args: argparse.Namespace) -> None:
    dest = pathlib.Path(args.path).resolve()
    project_name = _to_identifier(dest.name)

    _copy_template(TEMPLATES_DIR / "scaffold", dest)
    _substitute(dest, project_name)

    print(f"Project '{project_name}' created at '{dest}'.\n")
    print("Next steps:")
    print(f"  1. cd {dest}")
    print(f"  2. pip install -e .   # install the project's Python package")
    print(f"  3. dbt deps           # install the optimist dbt package")
    print(f"  4. dbt parse          # compile the manifest for Dagster")
    print(f"  5. dagster dev        # start the platform at http://localhost:3000")
    print(f"\nSee data-instructions.md or hand it to your AI assistant at the start of a session so it")
    print(f"knows the toolkit's conventions, then start adding your data sources.")


def cmd_demo(args: argparse.Namespace) -> None:
    dest = (
        pathlib.Path(args.path).resolve()
        if args.path
        else pathlib.Path.cwd() / "optimist-demo"
    )
    _copy_template(TEMPLATES_DIR / "demo", dest)
    print(f"NOAA demo project created at '{dest}'.\n")
    print("Next steps:")
    print(f"  1. cd {dest}")
    print(f"  2. pip install -e .   # install the demo's Python package")
    print(f"  3. dbt deps           # install the optimist dbt package")
    print(f"  4. Download the Guam 2025 AIS zone file from https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/data/ais/guam/index-guam.html")
    print(f"     and save it as data/guam_2025.csv inside the project folder")
    print(f"  5. dbt parse          # compile the manifest for Dagster")
    print(f"  6. dagster dev        # start the platform at http://localhost:3000")
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
    print(f"  DuckDB:  {config.duckdb_path}")
    print(f"  Dagster: {config.dagster_graphql_url}")
    print(f"  Marimo:  {config.marimo_url}")
    print()

    if args.open:
        import threading
        import webbrowser
        url = f"http://{'localhost' if args.host == '127.0.0.1' else args.host}:{args.port}"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app = create_app()
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


def _terminate_tree(proc: subprocess.Popen) -> None:
    """
    Kill the whole process tree, not just the launcher.

    `dagster dev` supervises a webserver, a daemon, and gRPC code-server children.
    proc.terminate() signals only the launcher, orphaning the grandchildren -- they
    keep holding port 3000 and spawning dbt runs after datavloot has exited, so every
    failed start leaves debris that interferes with the next one.
    """
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # taskkill walks the tree itself: /T includes children, /F forces.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


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

    print("Starting Dagster…")
    # POSIX: own session, so the whole tree can be signalled as one group.
    dagster_proc = subprocess.Popen(
        ["dagster", "dev"],
        start_new_session=(os.name != "nt"),
    )

    print(f"Waiting for Dagster to be ready at {graphql_url}…", flush=True)
    error = _wait_for_dagster(dagster_proc, graphql_url)
    if error:
        _terminate_tree(dagster_proc)
        sys.exit(f"Error: {error}")

    print("Dagster is ready.")

    try:
        cmd_crowsnest(args)
    finally:
        print("\nShutting down Dagster…")
        _terminate_tree(dagster_proc)


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
