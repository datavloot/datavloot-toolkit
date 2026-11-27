"""
Connect your own GitHub account: `uv run python -m github_platform.connect`.

Asks for your username and a read-only token (README: 'Use your own GitHub
data'), saves them in .env and checks that GitHub accepts them. From the next
pipeline run on, the project loads your own repositories and history instead
of the sample.
"""

import sys

import requests

from datavloot_platform import remote

from . import github


def main() -> None:
    print("Connecting a GitHub account to this project.")
    print("This needs a fine-grained personal access token (README: 'Use your own GitHub data').")
    try:
        # Asks for what .env.example lists and .env lacks; the token without echoing it.
        remote.fill_env(github.PROJECT_DIR)
    except remote.RemoteError as e:
        sys.exit(f"Error: {e}")
    username, token = github.setting("GITHUB_USERNAME"), github.setting("GITHUB_TOKEN")
    if not (username and token):
        sys.exit(f"Error: GITHUB_USERNAME and GITHUB_TOKEN must both be set in {github.ENV_FILE}.")

    response = requests.get(f"{github.API_URL}/user", timeout=30, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    if response.status_code == 401:
        sys.exit(f"Error: GitHub does not accept the token in {github.ENV_FILE} (expired or mistyped). "
                 "Make a new one and replace GITHUB_TOKEN there.")
    response.raise_for_status()
    login = response.json()["login"]
    if login.lower() != username.lower():
        sys.exit(f"Error: the token belongs to {login}, not to {username}. Fix GITHUB_USERNAME or the "
                 f"token in {github.ENV_FILE}.")
    print(f"\nConnected as {login}.")
    print("Next: in the Crows Nest, open Pipelines and click Materialize all. From then on the tables")
    print("show your own repositories, commits and contributions instead of the sample; a schedule")
    print("refreshes them every morning while Datavloot runs (restart it to switch that on).")


if __name__ == "__main__":
    main()
