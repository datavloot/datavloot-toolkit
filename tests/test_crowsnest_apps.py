"""
The Crows Nest's Dashboards panel (routes/apps.py): the project's apps/ folder,
served with `marimo run`.

On a laptop the Crows Nest starts one apps server for every app and keeps it;
behind a proxy (the Falcon) the apps are a service of their own, which it only
links to. A name from the browser never reaches outside apps/.
"""

import pytest

pytest.importorskip("duckdb", reason="duckdb is not installed")
pytest.importorskip("fastapi", reason="fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from datavloot_platform.crowsnest import config as cn_config  # noqa: E402
from datavloot_platform.crowsnest.routes import apps  # noqa: E402

DASHBOARD = '''import marimo

app = marimo.App(width="full", app_title="Vessel traffic")
'''


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    import duckdb

    db = tmp_path / "p.duckdb"
    duckdb.connect(str(db)).close()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CROWSNEST_DUCKDB_PATH", str(db))
    for var in ("CROWSNEST_AUTH_TOKEN", "CROWSNEST_APPS_URL", "CROWSNEST_APPS_PUBLIC_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(apps, "_apps_process", None)

    def make(with_apps=True, **env) -> TestClient:
        if with_apps:
            (tmp_path / "apps").mkdir(exist_ok=True)
            (tmp_path / "apps" / "traffic.py").write_text(DASHBOARD, encoding="utf-8")
            (tmp_path / "apps" / "plain.py").write_text("import marimo\n", encoding="utf-8")
        for var, value in env.items():
            monkeypatch.setenv(var, value)
        cn_config.reset_config()
        from datavloot_platform.crowsnest.server import create_app
        return TestClient(create_app())

    yield make
    cn_config.reset_config()


class _FakeProcess:
    def poll(self):
        return None

    def kill(self):
        pass


def test_lists_apps_with_their_titles(make_client):
    listed = make_client().get("/api/apps/list").json()
    assert listed == {
        "apps": [
            {"name": "plain.py", "title": "plain"},
            {"name": "traffic.py", "title": "Vessel traffic"},
        ],
        "available": True,
    }


def test_a_project_without_apps_says_so(make_client):
    assert make_client(with_apps=False).get("/api/apps/list").json() == {"apps": [], "available": False}


@pytest.mark.parametrize("name", ["../notebooks/explore.py", "..\\secret.py", "traffic.txt", "missing.py"])
def test_open_stays_inside_apps(make_client, monkeypatch, name):
    monkeypatch.setattr(apps, "start_marimo", lambda args: pytest.fail("started marimo for " + name))
    response = make_client().post("/api/apps/open", json={"name": name})
    assert response.status_code in (400, 404)


def test_a_laptop_starts_one_server_for_every_app(make_client, monkeypatch):
    calls = []

    def start(args):
        calls.append(args)
        return _FakeProcess()

    class _Answers:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            return _Answers()

    monkeypatch.setattr(apps, "start_marimo", start)
    monkeypatch.setattr(apps, "kill_port", lambda port: None)
    monkeypatch.setattr(apps.httpx, "AsyncClient", _Client)
    client = make_client()

    first = client.post("/api/apps/open", json={"name": "traffic.py"}).json()
    second = client.post("/api/apps/open", json={"name": "plain.py"}).json()

    assert first["url"] == "http://127.0.0.1:2719/?file=traffic.py"
    assert second["url"] == "http://127.0.0.1:2719/?file=plain.py"
    assert calls == [["run", "apps", "--headless", "--no-token", "--port", "2719"]], "one server for every app"


def test_an_apps_service_is_linked_to_not_started(make_client, monkeypatch):
    monkeypatch.setattr(apps, "start_marimo", lambda args: pytest.fail("started marimo next to the apps service"))
    monkeypatch.setattr(apps, "kill_port", lambda port: pytest.fail("killed a port next to the apps service"))
    client = make_client(CROWSNEST_APPS_PUBLIC_URL="https://apps.example.nl/")

    opened = client.post("/api/apps/open", json={"name": "traffic.py"}).json()
    assert opened["url"] == "https://apps.example.nl/?file=traffic.py"
    assert client.get("/api/services").json()["apps_url"] == "https://apps.example.nl"


def test_a_laptop_links_the_local_apps_server(make_client):
    assert make_client().get("/api/services").json()["apps_url"] == "http://127.0.0.1:2719"
