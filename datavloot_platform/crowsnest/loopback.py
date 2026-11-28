"""
Host and Origin checks for a Crows Nest that listens on loopback.

On a laptop the Crows Nest has no sign-in: binding 127.0.0.1 is the boundary.
A browser does not respect that boundary by itself. Any web page the user has
open can send requests to 127.0.0.1, and a hostile domain can point its DNS at
127.0.0.1 so that the browser treats the Crows Nest as part of that domain.
Both arrive with something the Crows Nest can see: a Host that is not a
loopback name, or an Origin that is not its own. Refusing those keeps the API,
including the SQL editor that may write on loopback, to this machine's own
programs and to pages the Crows Nest served itself.

Requests without an Origin pass: curl, scripts and agents send none, and a
browser leaves it off same-origin GETs.
"""

import os
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def _split(netloc: str, default_port: int) -> tuple[str, int] | None:
    """(hostname, port) of a Host header or an origin's netloc, or None if malformed."""
    if not netloc or "@" in netloc:
        return None
    try:
        parts = urlsplit(f"//{netloc}")
        return (parts.hostname or "", parts.port or default_port)
    except ValueError:
        return None


def _origin(origin: str) -> tuple[str, int] | None:
    """(hostname, port) of an http origin, or None for anything else ("null" included)."""
    scheme, sep, netloc = origin.strip().partition("://")
    if scheme.lower() != "http" or not sep or "/" in netloc:
        return None
    return _split(netloc, 80)


def dev_origins() -> frozenset[tuple[str, int]]:
    """
    The origins CROWSNEST_DEV_ORIGIN lets through besides the Crows Nest's own.

    For `npm run dev` (CONTRIBUTING.md): next.config.js proxies /api with the
    Crows Nest's Host but the dev server's Origin. Opt-in and exact, because
    whatever else serves pages on that port would get the API too. Only
    loopback names: this must never open the API to another site.
    """
    allowed = set()
    for entry in (os.environ.get("CROWSNEST_DEV_ORIGIN") or "").split(","):
        if not entry.strip():
            continue
        parsed = _origin(entry)
        if parsed is None or parsed[0] not in _LOOPBACK_NAMES:
            raise ValueError(
                f"CROWSNEST_DEV_ORIGIN={entry.strip()!r} is not understood: give the "
                "`npm run dev` page's origin, such as http://localhost:3001, or leave it unset."
            )
        allowed.add(parsed)
    return frozenset(allowed)


class LoopbackGuardMiddleware:
    """
    Refuse a request whose Host is not a loopback name (421), or whose Origin
    is not the Crows Nest's own or one in CROWSNEST_DEV_ORIGIN (403).

    Plain ASGI rather than BaseHTTPMiddleware, so it covers every route the app
    mounts -- the static dashboard, streaming responses and websockets included.
    """

    def __init__(self, app, bind_host: str):
        self.app = app
        bind = bind_host.strip().strip("[]").lower()
        self.names = _LOOPBACK_NAMES | {bind}
        # What the 421 tells the user to open: only names that reach this bind.
        # localhost finds 127.0.0.1 and ::1, but not another address in 127/8.
        if bind in ("localhost", "127.0.0.1"):
            self.addresses = ["localhost", "127.0.0.1"]
        elif bind == "::1":
            self.addresses = ["localhost", "[::1]"]
        else:
            self.addresses = [f"[{bind}]" if ":" in bind else bind]
        self.dev_origins = dev_origins()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {}
        for name, value in scope["headers"]:
            headers.setdefault(name.decode("latin-1").lower(), []).append(value.decode("latin-1"))

        # A repeated Host or Origin is refused outright: servers and proxies
        # disagree on which copy counts.
        hosts = headers.get("host", [])
        host = _split(hosts[0], 80) if len(hosts) == 1 else None
        if host is None or host[0] not in self.names:
            port = (scope.get("server") or (None, 8080))[1]
            return await self._refuse(
                scope, receive, send, 421,
                "This address does not reach the Crows Nest. Open it at "
                + " or ".join(f"http://{a}:{port}" for a in self.addresses) + ".",
            )

        origins = headers.get("origin")
        if origins is not None and (len(origins) != 1 or not self._allowed_origin(origins[0], host[1])):
            return await self._refuse(scope, receive, send, 403, "Cross-origin request refused.")

        return await self.app(scope, receive, send)

    def _allowed_origin(self, origin: str, port: int) -> bool:
        parsed = _origin(origin)
        if parsed is None:
            return False
        return (parsed[0] in self.names and parsed[1] == port) or parsed in self.dev_origins

    @staticmethod
    async def _refuse(scope, receive, send, status: int, detail: str):
        if scope["type"] == "websocket":
            # Closing before accepting is how ASGI refuses the handshake.
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
