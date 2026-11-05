"""
The Crows Nest's Shut down button: POST /api/shutdown.

Started from a shortcut, Datavloot runs without a window to close, so the
Crows Nest offers to stop it. Only on a laptop: on a shared host anyone
signed in could stop the service for everyone.
"""

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest.server import create_app  # noqa: E402


class FakeServer:
    """Stands in for the uvicorn.Server cli.cmd_crowsnest runs the app in."""
    should_exit = False


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CROWSNEST_AUTH_TOKEN", raising=False)
    # Never a real Dagster: a running one on :3000 would get its runs cancelled.
    monkeypatch.setenv("CROWSNEST_DAGSTER_URL", "http://127.0.0.1:9/graphql")
    cn_config.reset_config()
    yield
    cn_config.reset_config()


@pytest.fixture
def cancelled(monkeypatch):
    """Records cli.cancel_runs calls instead of making them."""
    from datavloot_platform import cli

    calls = []
    monkeypatch.setattr(cli, "cancel_runs", lambda url, **kw: calls.append(url) or ["r1"])
    return calls


def _app(host, server=True):
    app = create_app(host=host)
    if server:
        app.state.server = FakeServer()
    return app


def test_on_a_laptop_it_cancels_runs_then_asks_the_server_to_exit(cancelled):
    app = _app("127.0.0.1")
    client = TestClient(app)
    assert client.get("/api/services").json()["can_shutdown"] is True

    r = client.post("/api/shutdown")
    assert r.status_code == 200, r.text
    assert r.json()["cancelled_runs"] == ["r1"]
    assert cancelled == ["http://127.0.0.1:9/graphql"]
    assert app.state.server.should_exit is True


@pytest.mark.parametrize("host", ["0.0.0.0", None])
def test_on_a_shared_host_it_is_refused(host, cancelled):
    app = _app(host)
    client = TestClient(app)
    assert client.get("/api/services").json()["can_shutdown"] is False

    r = client.post("/api/shutdown")
    assert r.status_code == 403
    assert app.state.server.should_exit is False
    assert cancelled == [], "a refused shutdown cancels nothing"


def test_without_a_server_of_its_own_there_is_nothing_to_stop(cancelled):
    """An app not run by `datavloot start` or `launch` (another ASGI server, a test)."""
    client = TestClient(_app("127.0.0.1", server=False))
    assert client.get("/api/services").json()["can_shutdown"] is False
    assert client.post("/api/shutdown").status_code == 409
    assert cancelled == []


# --------------------------------------------------------------------------
# cli.cancel_runs, against a stand-in for Dagster
# --------------------------------------------------------------------------

@pytest.fixture
def dagster(monkeypatch):
    httpx = pytest.importorskip("httpx")
    import json

    state = {"runs": [], "cancelled": [], "statuses": None}

    def handler(request):
        body = json.loads(request.content)
        if "terminateRun" in body["query"]:
            state["cancelled"].append(body["variables"]["runId"])
            return httpx.Response(200, json={"data": {"terminateRun": {"__typename": "TerminateRunSuccess"}}})
        state["statuses"] = body["variables"]["statuses"]
        return httpx.Response(200, json={"data": {"runsOrError": {"__typename": "Runs", "results": state["runs"]}}})

    transport = httpx.MockTransport(handler)

    def post(url, **kwargs):
        kwargs.pop("timeout", None)
        with httpx.Client(transport=transport) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", post)
    return state


def test_shutdown_cancels_every_active_run(dagster):
    from datavloot_platform import cli

    dagster["runs"] = [{"runId": "a", "updateTime": 10.0}, {"runId": "q", "updateTime": 20.0}]
    assert cli.cancel_runs("http://dagster/graphql") == ["a", "q"]
    assert set(dagster["statuses"]) == {"STARTING", "STARTED", "CANCELING", "QUEUED"}


def test_at_start_only_runs_left_by_an_earlier_dagster_are_cancelled(dagster):
    """A run this Dagster started (a sensor, a schedule) was updated after it started."""
    from datavloot_platform import cli

    dagster["runs"] = [{"runId": "left", "updateTime": 100.0}, {"runId": "new", "updateTime": 205.0}]
    cancelled = cli.cancel_runs(
        "http://dagster/graphql", statuses=("STARTING", "STARTED", "CANCELING"), not_updated_since=200.0
    )
    assert cancelled == ["left"]
    assert dagster["cancelled"] == ["left"]
    assert "QUEUED" not in dagster["statuses"], "a queued run waits for this Dagster; it is not left over"


def test_an_unreachable_dagster_cancels_nothing_and_does_not_raise():
    pytest.importorskip("httpx")
    from datavloot_platform import cli

    assert cli.cancel_runs("http://127.0.0.1:9/graphql") == []
