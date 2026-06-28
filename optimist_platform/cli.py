import argparse
import pathlib
import shutil
import sys

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
    print(f"\nSee data-instructions.md to start adding your data sources.")


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


def cmd_crowsnest(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        sys.exit(
            "Error: uvicorn is required for the Crows Nest. "
            "Install it with: pip install 'optimist-toolkit[crowsnest]'"
        )

    from optimist_platform.crowsnest.config import get_config
    from optimist_platform.crowsnest.server import create_app

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
