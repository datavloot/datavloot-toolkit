#!/usr/bin/env bash
# Install Datavloot and open the Crows Nest on the NOAA demo, in one command:
#
#   curl -LsSf https://datavloot.nl/install-demo.sh | bash
#
# No Python, git or admin rights needed. The script:
#   1. installs uv (https://docs.astral.sh/uv/) for the current user, if missing
#   2. creates the demo project in ~/optimist-demo with `datavloot demo`
#   3. gives it its own Python and packages (`uv sync`), and runs `dbt deps` and `dbt parse`
#   4. starts Dagster and the Crows Nest, opens http://localhost:8080 and, the
#      first time, starts the run that downloads the demo data and builds the models
#
# Running it again starts the existing demo; it never overwrites one. For a new,
# empty project of your own there is new-project.sh, and for a project from its
# repository install-project.sh.
#
# Settings, as environment variables (`curl ... | DATAVLOOT_DIR=~/demo bash`):
#   DATAVLOOT_DIR      where the demo goes (default: ~/optimist-demo)
#   DATAVLOOT_VERSION  a toolkit version, e.g. 0.4.0 (default: the latest release)
#   DATAVLOOT_FROM     install the toolkit from here instead of PyPI, e.g. a checkout
#
# Written for the bash 3.2 that macOS ships.

set -euo pipefail

# --- Shared by install-demo.sh, new-project.sh and install-project.sh ------------
# Each script is served as one file (`curl | bash` fetches nothing else), so this
# part is repeated in all three. tests/test_install_scripts.py keeps them equal.

PYTHON_VERSION=3.12
DAGSTER_PORT=3000
CROWSNEST_PORT=8080

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mError: %s\033[0m\n' "$1" >&2; exit 1; }

run_step() {
    local what="$1"; shift
    step "$what"
    "$@" || fail "$what failed (exit code $?). The output above says why."
}

is_project() { [ -f "$1/dbt_project.yml" ] && [ -f "$1/pyproject.toml" ]; }

full_path() {
    # ~ expanded; a relative path made absolute against the current folder.
    local dir="$1"
    case "$dir" in "~"*) dir="$HOME${dir#\~}" ;; esac
    case "$dir" in /*) ;; *) dir="$PWD/$dir" ;; esac
    printf '%s' "$dir"
}

check_project_dir() {
    # Sets EXISTING to true when the folder holds a Datavloot project, to false
    # when it is free. An empty folder is removed: `datavloot demo` and `new`
    # create it themselves.
    EXISTING=false
    if [ -e "$1" ]; then
        if is_project "$1"; then
            EXISTING=true
        elif [ -d "$1" ] && [ -z "$(ls -A "$1")" ]; then
            rmdir "$1"
        else
            fail "'$1' already exists and is not a Datavloot project. Nothing in it was changed. Set DATAVLOOT_DIR to another folder and run this again."
        fi
    fi
}

check_internet() {
    curl -fsSI --max-time 20 https://pypi.org/simple/datavloot/ >/dev/null 2>&1 \
        || fail "Cannot reach pypi.org. Check the internet connection. Behind a proxy, set HTTPS_PROXY (for example export HTTPS_PROXY=http://proxy:8080) and run this again."
}

install_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        if [ ! -x "$HOME/.local/bin/uv" ]; then
            # uv's own installer, for the current user: no admin rights.
            run_step "Installing uv" sh -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
        fi
        export PATH="$HOME/.local/bin:$PATH"
        command -v uv >/dev/null 2>&1 \
            || fail "uv was installed but is not found in ~/.local/bin. Open a new terminal and run this again."
    fi
    echo "uv: $(uv --version)"
}

toolkit_source() {
    if [ -n "${DATAVLOOT_FROM:-}" ]; then
        printf '%s' "$DATAVLOOT_FROM"
    elif [ -n "${DATAVLOOT_VERSION:-}" ]; then
        printf '%s' "datavloot[optimist]==$DATAVLOOT_VERSION"
    else
        printf '%s' "datavloot[optimist]@latest"
    fi
}

install_environment() {
    # In the project folder. Also repairs a project an earlier attempt left
    # halfway, and is quick when nothing is missing. An installed project gets
    # exactly the versions its maintainer locked.
    local locked=""
    if [ -f uv.lock ] && [ -f .datavloot/install.json ]; then locked="--locked"; fi
    run_step "Installing Python $PYTHON_VERSION and the project's packages" \
        uv sync --python "$PYTHON_VERSION" $locked
    if [ ! -d dbt_packages ]; then
        run_step "Installing the dbt packages" uv run --no-sync dbt deps
    fi
    run_step "Compiling the dbt project" uv run --no-sync dbt parse
}

port_user() {
    # Who listens on the port; empty when it is free.
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN -Fc 2>/dev/null | sed -n 's/^c//p' | head -n 1
    elif (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
        echo "another program"
    fi
}

assert_ports_free() {
    local port name user
    for port in "$CROWSNEST_PORT" "$DAGSTER_PORT"; do
        if [ "$port" = "$CROWSNEST_PORT" ]; then name="the Crows Nest"; else name="Dagster"; fi
        user="$(port_user "$port")"
        if [ -n "$user" ]; then
            fail "Port $port, which $name needs, is in use by $user. If Datavloot is already running, open http://localhost:$CROWSNEST_PORT. Otherwise close that program and run this again."
        fi
    done
}

start_help() {
    step "Starting Dagster and the Crows Nest"
    echo "The Crows Nest opens at http://localhost:$CROWSNEST_PORT. Keep this terminal open;"
    echo "closing it or pressing Ctrl+C stops Datavloot. To start it again later:"
    # The project's own datavloot rather than `uv run`: a terminal opened before
    # uv was installed does not have uv on its PATH yet.
    printf '\033[33m    cd "%s" && .venv/bin/datavloot start\033[0m\n' "$1"
    if [ "$(uname -s)" = "Darwin" ]; then
        echo "Or have it start at every login, with an app in ~/Applications:"
        printf '\033[33m    cd "%s" && .venv/bin/datavloot autostart on\033[0m\n' "$1"
        echo "Or only the app, without starting at login:"
        printf '\033[33m    cd "%s" && .venv/bin/datavloot shortcut on\033[0m\n' "$1"
    fi
}

# --- End of the shared part -------------------------------------------------------

main() {
    printf '\033[36mDatavloot: installing the toolkit and the NOAA demo\033[0m\n'
    local dir
    dir="$(full_path "${DATAVLOOT_DIR:-$HOME/optimist-demo}")"
    check_project_dir "$dir"

    check_internet
    install_uv

    if $EXISTING; then
        printf '\nFound the demo in %s; its files stay as they are.\n' "$dir"
    else
        # DATAVLOOT_INSTALLER: `datavloot demo` leaves out the steps this script takes itself.
        run_step "Creating the demo project in $dir" \
            env DATAVLOOT_INSTALLER=1 uvx --python "$PYTHON_VERSION" --from "$(toolkit_source)" datavloot demo "$dir"
    fi

    cd "$dir"
    install_environment
    assert_ports_free
    start_help "$dir"
    if ! $EXISTING; then
        echo "The first run downloads the demo's AIS data (41 MB) and builds the models;"
        echo "follow it in the Crows Nest's Pipelines panel."
    fi
    echo
    # The demo fetches its own data, so it can run straight away.
    if $EXISTING; then
        exec uv run --no-sync datavloot start
    else
        exec uv run --no-sync datavloot start --run
    fi
}

# Everything is inside main, so a download cut off halfway runs nothing.
main "$@"
