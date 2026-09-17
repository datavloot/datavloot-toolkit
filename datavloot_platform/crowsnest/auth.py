"""
Authentication for the Crows Nest. Two modes, both off by default.

Token mode (CROWSNEST_AUTH_TOKEN) -- the Optimist on a VM
    One shared secret. On a laptop the server binds to localhost and a password
    would be friction with no benefit; on a VM this is the minimum that makes the
    dashboard safe to expose. Two ways to present it, so both a browser and a
    script work without the frontend needing to know anything about auth:

        Authorization: Bearer <token>           scripts, curl, fetch()
        Authorization: Basic  <base64 u:token>  browsers, via the native prompt

    The Basic form is why a 401 carries WWW-Authenticate: the browser then asks
    for credentials itself. Any username is accepted; the password is the token.

OIDC mode (CROWSNEST_OIDC_ISSUER) -- the Valk
    The Crows Nest sits behind SRDP's Traefik + oauth2-proxy + Zitadel gate, which
    already logged the user in. But "behind the proxy" is not a boundary: any
    container on the internal network can call the Crows Nest directly with made-up
    X-Auth-Request-* headers (SRDP's ADR-0008 says the same). So the Crows Nest
    validates the access token itself, on every request:

        JWT access token   -> signature against the issuer's JWKS, issuer, expiry
        opaque token       -> the issuer's userinfo endpoint (slower; see docs/valk.md
                              for the Zitadel setting that makes tokens JWTs)

    Roles come from Zitadel's project-roles claim and follow SRDP's ADR-0005
    names: reader < writer < admin. Reads need reader; anything that changes state
    (pipeline triggers, notebook launches) needs writer. A user with no role gets
    CROWSNEST_OIDC_DEFAULT_ROLE (reader by default; `none` to deny).
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hmac
import os
import ssl
import time

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Left open so a reverse proxy or uptime check can see the server is alive
# without holding the token.
_PUBLIC_PATHS = frozenset({"/api/health"})


# ---------------------------------------------------------------------------
# Token mode
# ---------------------------------------------------------------------------

def get_auth_token() -> str | None:
    """The configured token, or None when auth is disabled."""
    return os.environ.get("CROWSNEST_AUTH_TOKEN") or None


def _presented_token(header: str | None) -> str | None:
    """Pull a token out of an Authorization header, whichever scheme was used."""
    if not header:
        return None

    scheme, _, value = header.partition(" ")
    value = value.strip()
    if not value:
        return None

    scheme = scheme.lower()
    if scheme == "bearer":
        return value
    if scheme == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None
        _, sep, password = decoded.partition(":")
        return password if sep else None
    return None


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Require the configured token on every request, when one is configured."""

    async def dispatch(self, request, call_next):
        expected = get_auth_token()
        # OIDC mode owns authentication when it is configured; a stray token
        # variable must not add a second, unrelated password prompt on top.
        if expected is None or get_oidc_settings() is not None or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        presented = _presented_token(request.headers.get("authorization"))
        # compare_digest rather than == so a wrong token cannot be recovered by
        # timing how long the comparison took.
        if presented is not None and hmac.compare_digest(presented, expected):
            return await call_next(request)

        return JSONResponse(
            {"detail": "Missing or invalid credentials."},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Crows Nest"'},
        )


# ---------------------------------------------------------------------------
# OIDC mode
# ---------------------------------------------------------------------------

ROLE_ORDER = {"reader": 1, "writer": 2, "admin": 3}
ZITADEL_ROLES_CLAIM = "urn:zitadel:iam:org:project:roles"

# Mutating requests under these prefixes change platform state (launch a run,
# start or kill a notebook). Everything else the Crows Nest does is a read, and
# that includes POST /api/query/execute: the connection it runs on is read-only.
_WRITE_PREFIXES = ("/api/pipelines", "/api/notebooks")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Access-token headers oauth2-proxy can hand us, in order of preference.
_TOKEN_HEADERS = ("x-auth-request-access-token", "x-forwarded-access-token")


@dataclasses.dataclass(frozen=True)
class OidcSettings:
    issuer: str
    audience: str | None
    default_role: str          # reader | none
    insecure_tls: bool


def get_oidc_settings() -> OidcSettings | None:
    issuer = os.environ.get("CROWSNEST_OIDC_ISSUER")
    if not issuer:
        return None
    default_role = (os.environ.get("CROWSNEST_OIDC_DEFAULT_ROLE") or "reader").lower()
    if default_role not in ("reader", "none"):
        default_role = "reader"
    return OidcSettings(
        issuer=issuer.rstrip("/"),
        audience=os.environ.get("CROWSNEST_OIDC_AUDIENCE") or None,
        default_role=default_role,
        insecure_tls=(os.environ.get("CROWSNEST_OIDC_INSECURE_TLS") or "").lower() in ("1", "true", "yes"),
    )


def extract_token(headers) -> str | None:
    """The bearer token from Authorization or from oauth2-proxy's forwarded header."""
    auth = headers.get("authorization")
    if auth:
        scheme, _, value = auth.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    for name in _TOKEN_HEADERS:
        value = headers.get(name)
        if value:
            return value.strip()
    return None


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and all(token.split("."))


def roles_from_claims(claims: dict) -> set[str]:
    """
    Role names out of a token, whatever shape the issuer used.

    Zitadel: {"urn:zitadel:iam:org:project:roles": {"reader": {"<org id>": "<org domain>"}}}
    Generic: {"roles": ["reader", "writer"]}
    Only names the Crows Nest knows are kept.
    """
    found: set[str] = set()
    zitadel = claims.get(ZITADEL_ROLES_CLAIM)
    if isinstance(zitadel, dict):
        found.update(zitadel.keys())
    elif isinstance(zitadel, list):
        found.update(str(r) for r in zitadel)
    generic = claims.get("roles")
    if isinstance(generic, list):
        found.update(str(r) for r in generic)
    elif isinstance(generic, str):
        found.update(generic.split())
    return {r.lower() for r in found if r.lower() in ROLE_ORDER}


def highest_role(roles: set[str]) -> str | None:
    return max(roles, key=ROLE_ORDER.__getitem__) if roles else None


def required_role(method: str, path: str) -> str:
    if method.upper() in _SAFE_METHODS:
        return "reader"
    return "writer" if path.startswith(_WRITE_PREFIXES) else "reader"


class OidcError(Exception):
    """A token that must be refused. The message is safe to return to the caller."""


class OidcVerifier:
    """
    Validates tokens for one issuer. Discovery and JWKS are fetched lazily, once.

    `signing_key` and `userinfo` are the two network touch points; tests replace
    them. Everything else is pure.
    """

    _USERINFO_TTL = 60  # seconds; a revoked opaque token stops working within this

    def __init__(self, settings: OidcSettings):
        self.settings = settings
        self._discovery: dict | None = None
        self._jwks_client = None
        self._userinfo_cache: dict[str, tuple[float, dict]] = {}

    # -- network -----------------------------------------------------------

    def _ssl_context(self):
        if not self.settings.insecure_tls:
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def discovery(self) -> dict:
        if self._discovery is None:
            import httpx
            url = f"{self.settings.issuer}/.well-known/openid-configuration"
            resp = httpx.get(url, timeout=5.0, verify=not self.settings.insecure_tls)
            resp.raise_for_status()
            self._discovery = resp.json()
        return self._discovery

    def signing_key(self, token: str):
        """The public key that signed `token`, from the issuer's JWKS (cached)."""
        import jwt

        if self._jwks_client is None:
            jwks_uri = self.discovery().get("jwks_uri") or f"{self.settings.issuer}/oauth/v2/keys"
            kwargs = {"cache_keys": True}
            ctx = self._ssl_context()
            if ctx is not None:
                kwargs["ssl_context"] = ctx
            self._jwks_client = jwt.PyJWKClient(jwks_uri, **kwargs)
        return self._jwks_client.get_signing_key_from_jwt(token).key

    def userinfo(self, token: str) -> dict:
        """Claims for an opaque token, from the issuer, cached briefly per token."""
        import httpx

        now = time.monotonic()
        cached = self._userinfo_cache.get(token)
        if cached and cached[0] > now:
            return cached[1]
        try:
            endpoint = self.discovery().get("userinfo_endpoint") or f"{self.settings.issuer}/oidc/v1/userinfo"
            resp = httpx.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
                verify=not self.settings.insecure_tls,
            )
        except Exception as exc:  # issuer down or unreachable: cannot validate, so refuse
            raise OidcError(f"The issuer could not be reached: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            raise OidcError("The issuer did not accept this token.")
        try:
            claims = resp.json()
        except ValueError as exc:
            raise OidcError("The issuer returned an unreadable userinfo response.") from exc
        if len(self._userinfo_cache) > 512:
            self._userinfo_cache.clear()
        self._userinfo_cache[token] = (now + self._USERINFO_TTL, claims)
        return claims

    # -- pure ----------------------------------------------------------------

    def verify_jwt(self, token: str) -> dict:
        import jwt

        try:
            key = self.signing_key(token)
            options = {"require": ["exp", "iss"]}
            if self.settings.audience is None:
                options["verify_aud"] = False
            return jwt.decode(
                token,
                key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256"],
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                options=options,
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise OidcError(f"Invalid token: {exc.__class__.__name__}") from exc
        except Exception as exc:  # JWKS unreachable, malformed header, ...
            raise OidcError(f"Token could not be validated: {exc.__class__.__name__}") from exc

    def claims_for(self, token: str) -> dict:
        if looks_like_jwt(token):
            return self.verify_jwt(token)
        return self.userinfo(token)


_verifiers: dict[OidcSettings, OidcVerifier] = {}


def get_verifier(settings: OidcSettings) -> OidcVerifier:
    verifier = _verifiers.get(settings)
    if verifier is None:
        verifier = _verifiers[settings] = OidcVerifier(settings)
    return verifier


def reset_verifiers() -> None:
    """Drop cached verifiers (tests; also useful after rotating the issuer)."""
    _verifiers.clear()


def _principal(claims: dict, role: str) -> dict:
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name") or claims.get("preferred_username"),
        "role": role,
        "roles": sorted(roles_from_claims(claims)),
    }


class OidcAuthMiddleware(BaseHTTPMiddleware):
    """Validate the issuer's token on every request, when an issuer is configured."""

    async def dispatch(self, request, call_next):
        settings = get_oidc_settings()
        if settings is None or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        token = extract_token(request.headers)
        if token is None:
            return _unauthorized("No access token. Sign in through the platform's login page.")

        verifier = get_verifier(settings)
        try:
            # Both branches may touch the network the first time; keep them off the
            # event loop.
            claims = await run_in_threadpool(verifier.claims_for, token)
        except OidcError as exc:
            return _unauthorized(str(exc))
        except Exception as exc:  # never let a validation failure fall through as a 500
            return _unauthorized(f"Token could not be validated: {exc.__class__.__name__}")

        role = highest_role(roles_from_claims(claims))
        if role is None:
            if settings.default_role == "none":
                return _forbidden("Your account has no role on this project. Ask an admin for one.")
            role = settings.default_role

        needed = required_role(request.method, request.url.path)
        if ROLE_ORDER[role] < ROLE_ORDER[needed]:
            return _forbidden(f"This action needs the '{needed}' role; you have '{role}'.")

        request.state.user = _principal(claims, role)
        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        {"detail": detail},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="Crows Nest"'},
    )


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=403)
