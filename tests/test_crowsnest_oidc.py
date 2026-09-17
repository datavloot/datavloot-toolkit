"""
OIDC mode for the Crows Nest: the Valk behind SRDP's Zitadel gate.

The middleware validates every request's token itself; the two network calls
(JWKS, userinfo) are replaced here with an RSA key generated per test session.
Off unless CROWSNEST_OIDC_ISSUER is set, so nothing here touches the laptop case.
"""

import os
import time

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")
jwt = pytest.importorskip("jwt", reason="pyjwt is not installed")
pytest.importorskip("cryptography", reason="cryptography is not installed")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import auth  # noqa: E402
from datavloot_platform.crowsnest import config as cn_config  # noqa: E402

ISSUER = "https://auth.probe.valk.test"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key(), other


def _pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture
def client(tmp_path, monkeypatch, keypair) -> TestClient:
    private, public, _ = keypair
    import duckdb
    db = tmp_path / "p.duckdb"
    duckdb.connect(str(db)).close()

    monkeypatch.setenv("CROWSNEST_DUCKDB_PATH", str(db))
    monkeypatch.setenv("CROWSNEST_OIDC_ISSUER", ISSUER)
    monkeypatch.delenv("CROWSNEST_OIDC_DEFAULT_ROLE", raising=False)
    monkeypatch.delenv("CROWSNEST_OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("DATAVLOOT_VESSEL", raising=False)
    monkeypatch.chdir(tmp_path)

    # The two network touch points, replaced.
    monkeypatch.setattr(auth.OidcVerifier, "signing_key", lambda self, token: public)
    monkeypatch.setattr(auth.OidcVerifier, "discovery", lambda self: {})
    auth.reset_verifiers()
    cn_config.reset_config()

    from datavloot_platform.crowsnest.server import create_app
    yield TestClient(create_app())
    auth.reset_verifiers()
    cn_config.reset_config()


def make_token(keypair, *, roles=None, iss=ISSUER, exp_in=300, signer=None, zitadel_shape=True, **extra):
    private, _, _ = keypair
    claims = {"iss": iss, "sub": "u1", "email": "eva@example.nl", "exp": int(time.time()) + exp_in, **extra}
    if roles is not None:
        if zitadel_shape:
            claims[auth.ZITADEL_ROLES_CLAIM] = {r: {"1": "org.example"} for r in roles}
        else:
            claims["roles"] = list(roles)
    return jwt.encode(claims, _pem(signer or private), algorithm="RS256", headers={"kid": "k1"})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------

def test_no_token_is_401_with_a_bearer_challenge(client):
    r = client.get("/api/query/tables")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].lower().startswith("bearer")


def test_health_stays_public(client):
    assert client.get("/api/health").status_code == 200


def test_valid_token_reads(client, keypair):
    r = client.get("/api/query/tables", headers=bearer(make_token(keypair, roles=["reader"])))
    assert r.status_code == 200, r.text


def test_the_dashboard_itself_needs_a_token(client):
    assert client.get("/").status_code == 401


def test_token_from_oauth2_proxy_header_is_accepted(client, keypair):
    """oauth2-proxy hands the token over in X-Auth-Request-Access-Token, not Authorization."""
    r = client.get("/api/query/tables", headers={"X-Auth-Request-Access-Token": make_token(keypair, roles=["reader"])})
    assert r.status_code == 200, r.text


def test_me_reports_the_zitadel_role(client, keypair):
    r = client.get("/api/me", headers=bearer(make_token(keypair, roles=["reader", "writer"])))
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "eva@example.nl"
    assert body["user"]["role"] == "writer", "the highest granted role wins"
    assert body["user"]["roles"] == ["reader", "writer"]


@pytest.mark.parametrize("kwargs, why", [
    ({"exp_in": -60}, "expired"),
    ({"iss": "https://someone-else.test"}, "wrong issuer"),
    ({"signer": "other"}, "signed by a different key"),
])
def test_bad_tokens_are_refused(client, keypair, kwargs, why):
    if kwargs.get("signer") == "other":
        kwargs["signer"] = keypair[2]
    r = client.get("/api/query/tables", headers=bearer(make_token(keypair, roles=["reader"], **kwargs)))
    assert r.status_code == 401, why


def test_garbage_bearer_is_refused(client):
    assert client.get("/api/query/tables", headers=bearer("not.a.jwt")).status_code == 401


def test_reader_cannot_trigger_pipelines(client, keypair):
    """
    Mutations under /api/pipelines need writer. The check runs before routing, so
    it holds for endpoints that do not exist yet -- the v1.1 'Run' button included.
    """
    r = client.post("/api/pipelines/run", json={}, headers=bearer(make_token(keypair, roles=["reader"])))
    assert r.status_code == 403
    assert "writer" in r.json()["detail"]


def test_writer_passes_the_role_check(client, keypair):
    r = client.post("/api/pipelines/run", json={}, headers=bearer(make_token(keypair, roles=["writer"])))
    assert r.status_code not in (401, 403), "past auth; the route itself may not exist (404/405)"


def test_read_only_sql_is_a_read(client, keypair):
    """POST /api/query/execute runs on a read-only connection; reader is enough."""
    r = client.post("/api/query/execute", json={"sql": "SELECT 1"}, headers=bearer(make_token(keypair, roles=["reader"])))
    assert r.status_code == 200, r.text


def test_no_role_falls_back_to_the_default_role(client, keypair):
    r = client.get("/api/me", headers=bearer(make_token(keypair)))
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "reader"


def test_default_role_none_denies_the_roleless(client, keypair, monkeypatch):
    monkeypatch.setenv("CROWSNEST_OIDC_DEFAULT_ROLE", "none")
    auth.reset_verifiers()
    r = client.get("/api/query/tables", headers=bearer(make_token(keypair)))
    assert r.status_code == 403
    ok = client.get("/api/query/tables", headers=bearer(make_token(keypair, roles=["reader"])))
    assert ok.status_code == 200


def test_generic_roles_claim_also_works(client, keypair):
    r = client.get("/api/me", headers=bearer(make_token(keypair, roles=["admin"], zitadel_shape=False)))
    assert r.json()["user"]["role"] == "admin"


def test_opaque_token_goes_to_userinfo(client, monkeypatch):
    """Zitadel's default access token is opaque; the issuer is asked who it belongs to."""
    calls = []

    def fake_userinfo(self, token):
        calls.append(token)
        return {"sub": "u2", "email": "thijs@example.nl", auth.ZITADEL_ROLES_CLAIM: {"writer": {}}}

    monkeypatch.setattr(auth.OidcVerifier, "userinfo", fake_userinfo)
    r = client.get("/api/me", headers=bearer("opaque-token-value"))
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "writer"
    assert calls == ["opaque-token-value"]


def test_opaque_token_the_issuer_rejects_is_401(client, monkeypatch):
    def refuse(self, token):
        raise auth.OidcError("The issuer did not accept this token.")
    monkeypatch.setattr(auth.OidcVerifier, "userinfo", refuse)
    assert client.get("/api/me", headers=bearer("revoked")).status_code == 401


def test_static_token_mode_is_dormant_under_oidc(client, keypair, monkeypatch):
    """A leftover CROWSNEST_AUTH_TOKEN must not add a second password prompt."""
    monkeypatch.setenv("CROWSNEST_AUTH_TOKEN", "leftover")
    r = client.get("/api/query/tables", headers=bearer(make_token(keypair, roles=["reader"])))
    assert r.status_code == 200
    assert client.get("/api/query/tables", headers=bearer("leftover")).status_code == 401


# --------------------------------------------------------------------------
# Pure helpers

def test_required_role_table():
    assert auth.required_role("GET", "/api/pipelines/runs") == "reader"
    assert auth.required_role("POST", "/api/pipelines/run") == "writer"
    assert auth.required_role("DELETE", "/api/notebooks/stop") == "writer"
    assert auth.required_role("POST", "/api/query/execute") == "reader"


def test_roles_from_claims_ignores_unknown_names():
    claims = {auth.ZITADEL_ROLES_CLAIM: {"reader": {}, "superuser": {}}, "roles": ["Admin"]}
    assert auth.roles_from_claims(claims) == {"reader", "admin"}
    assert auth.highest_role(set()) is None
