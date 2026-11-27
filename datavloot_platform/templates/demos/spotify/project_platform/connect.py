"""
Connect your own Spotify account: `uv run python -m spotify_platform.connect`.

Logs in once in the browser (Authorization Code with PKCE, so no client secret
is stored) and saves the refresh token in .env. From the next pipeline run on,
the project loads your listening data instead of the sample. See the README,
"Use your own Spotify data", for the developer app this needs first.
"""

import base64
import hashlib
import http.server
import secrets
import sys
import time
import urllib.parse
import webbrowser

import requests

from datavloot_platform import remote

from . import spotify

LOGIN_TIMEOUT_SECONDS = 300


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _wait_for_code(redirect_uri: str, state: str) -> str:
    """Serve the redirect once, on the address the developer app was given, and return the code."""
    target = urllib.parse.urlsplit(redirect_uri)
    if target.scheme != "http" or target.hostname not in ("127.0.0.1", "[::1]", "::1"):
        sys.exit(f"Error: SPOTIFY_REDIRECT_URI must be a loopback address such as "
                 f"{spotify.DEFAULT_REDIRECT_URI}, not {redirect_uri}.")
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            query = dict(urllib.parse.parse_qsl(url.query))
            if url.path != (target.path or "/"):
                self.send_response(404)
                self.end_headers()
                return
            if query.get("state") != state:
                result["error"] = "the answer did not belong to this login (state differs)"
            elif "error" in query:
                result["error"] = query["error"]
            else:
                result["code"] = query.get("code", "")
            ok = "code" in result
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            message = ("Connected. You can close this tab and go back to the terminal."
                       if ok else f"Spotify did not connect: {result.get('error')}.")
            self.wfile.write(f"<!doctype html><title>Spotify</title><p>{message}</p>".encode("utf-8"))

        def log_message(self, *args):
            pass

    try:
        server = http.server.HTTPServer((target.hostname.strip("[]"), target.port or 80), Handler)
    except OSError as e:
        sys.exit(f"Error: cannot listen on {target.hostname}:{target.port} for Spotify's answer ({e}). "
                 "Close what uses that port, or choose another port in SPOTIFY_REDIRECT_URI and in "
                 "the developer app's Redirect URIs.")
    deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
    with server:
        # Other requests (the browser's favicon.ico) can come first: wait for the redirect itself.
        while not result and time.monotonic() < deadline:
            server.timeout = max(1.0, deadline - time.monotonic())
            server.handle_request()
    if "code" not in result:
        sys.exit(f"Error: Spotify did not connect: {result.get('error', 'no answer within five minutes')}.")
    return result["code"]


def main() -> None:
    print("Connecting a Spotify account to this project.")
    print("This needs a Spotify developer app (README: 'Use your own Spotify data').")
    try:
        # Asks for what .env.example lists and .env lacks: the client ID and the redirect URI.
        remote.fill_env(spotify.PROJECT_DIR)
    except remote.RemoteError as e:
        sys.exit(f"Error: {e}")
    client_id = spotify.setting("SPOTIFY_CLIENT_ID")
    redirect_uri = spotify.setting("SPOTIFY_REDIRECT_URI") or spotify.DEFAULT_REDIRECT_URI
    if not client_id:
        sys.exit(f"Error: no SPOTIFY_CLIENT_ID in {spotify.ENV_FILE}.")

    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)
    url = spotify.AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge_method": "S256",
        "code_challenge": _challenge(verifier),
        "scope": " ".join(spotify.SCOPES),
        "state": state,
    })
    print("\nLog in to Spotify in the browser window that opens. If none opens, go to:")
    print(f"  {url}\n")
    webbrowser.open(url)
    code = _wait_for_code(redirect_uri, state)

    response = requests.post(spotify.TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }, timeout=30)
    if not response.ok:
        sys.exit(f"Error: Spotify refused the login: {response.status_code} {response.text[:300]}")
    spotify.set_setting("SPOTIFY_REFRESH_TOKEN", response.json()["refresh_token"])

    me = spotify.Spotify(requests, client_id, spotify.setting("SPOTIFY_REFRESH_TOKEN")).get("/me")
    print(f"Connected as {me.get('display_name') or me['id']}. The refresh token is in {spotify.ENV_FILE}.")
    print("\nNext: in the Crows Nest, open Pipelines and click Materialize all. From then on the")
    print("tables show your own data instead of the sample. Restart Datavloot (datavloot start) to")
    print("turn on the schedule that collects your plays every 30 minutes.")


if __name__ == "__main__":
    main()
