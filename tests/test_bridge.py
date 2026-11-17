from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import pytest

from jobstreetracer import bridge
from jobstreetracer.bridge import BridgeServer, BridgeState
from jobstreetracer.config import ConfigError


@dataclass
class FakeSummary:
    scanned: int = 5
    new: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"scanned": self.scanned, "new": self.new}


class ServerRunner:
    """Run the real bridge handler on an ephemeral port and expose a tiny HTTP client."""

    def __init__(self, state: BridgeState) -> None:
        self.server = BridgeServer(("127.0.0.1", 0), state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        raw: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        data: bytes | None = None
        hdrs = dict(headers or {})
        if raw is not None:
            data = raw.encode("utf-8")
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        req = Request(self.base + path, data=data, headers=hdrs, method=method)
        try:
            with urlopen(req) as resp:
                return resp.status, _decode(resp.read())
        except HTTPError as exc:
            return exc.code, _decode(exc.read())

    def get(self, path: str, **kw: Any) -> tuple[int, Any]:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> tuple[int, Any]:
        return self.request("POST", path, **kw)

    def get_no_redirect(self, path: str) -> tuple[int, str | None]:
        """GET without following redirects; returns (status, Location header)."""
        req = Request(self.base + path, method="GET")

        class _NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return None

        opener = build_opener(_NoRedirect)
        try:
            resp = opener.open(req)
            return resp.status, resp.headers.get("Location")
        except HTTPError as exc:
            return exc.code, exc.headers.get("Location")

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _decode(raw: bytes) -> Any:
    text = raw.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@pytest.fixture
def run_server(tmp_path: Path):
    runners: list[ServerRunner] = []

    def _factory(**state_kwargs: Any) -> ServerRunner:
        state_kwargs.setdefault("config_path", None)
        state_kwargs.setdefault("static_dir", None)
        runner = ServerRunner(BridgeState(**state_kwargs))
        runners.append(runner)
        return runner

    yield _factory
    for runner in runners:
        runner.stop()


# --------------------------------------------------------------------------
# GET endpoints
# --------------------------------------------------------------------------
def test_health_reports_version(run_server) -> None:
    server = run_server()
    status, payload = server.get("/api/health")
    assert status == 200
    assert payload == {"ok": True, "version": bridge.__version__}


def test_feed_returns_built_feed(run_server, monkeypatch) -> None:
    sentinel_config = object()
    monkeypatch.setattr(bridge, "load_config", lambda path: sentinel_config)

    seen: dict[str, Any] = {}

    def fake_build_feed(config):
        seen["config"] = config
        return {"version": 1, "jobs": [{"id": "abc"}]}

    monkeypatch.setattr(bridge, "build_feed", fake_build_feed)

    server = run_server(config_path=Path("/does/not/matter.toml"))
    status, payload = server.get("/api/feed")

    assert status == 200
    assert payload["jobs"][0]["id"] == "abc"
    # load_config received the configured path; build_feed received its config.
    assert seen["config"] is sentinel_config


def test_feed_config_error_is_service_unavailable(run_server, monkeypatch) -> None:
    def boom(path):
        raise ConfigError("no config at path")

    monkeypatch.setattr(bridge, "load_config", boom)

    server = run_server()
    status, payload = server.get("/api/feed")
    assert status == 503
    assert "no config at path" in payload["error"]


def test_feed_unexpected_error_is_internal_server_error(run_server, monkeypatch) -> None:
    def boom(path):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(bridge, "load_config", boom)

    server = run_server()
    status, payload = server.get("/api/feed")
    assert status == 500
    assert payload["error"] == "db exploded"


def test_setup_status_endpoint(run_server, monkeypatch) -> None:
    monkeypatch.setattr(
        bridge.bridge_setup,
        "setup_status",
        lambda *, host, port: {"ok": True, "host": host, "port": port},
    )
    server = run_server()
    status, payload = server.get("/api/setup/status")
    assert status == 200
    assert payload["ok"] is True
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == int(server.base.rsplit(":", 1)[1])


def test_root_redirects_to_pwa(run_server) -> None:
    # Requesting the bare root issues a 302 to /jobstreetracer/.
    server = run_server()
    status, location = server.get_no_redirect("/")
    assert status == 302
    assert location == "/jobstreetracer/"


def test_root_follows_to_static_missing_message(run_server) -> None:
    # With no static dir configured, the followed redirect lands on the JSON error.
    server = run_server()
    status, payload = server.get("/jobstreetracer/")
    assert status == 404
    assert payload["error"] == "static dir not configured"


# --------------------------------------------------------------------------
# POST guards
# --------------------------------------------------------------------------
def test_post_requires_bridge_header(run_server) -> None:
    server = run_server()
    status, payload = server.post("/api/refresh", body={})
    assert status == 403
    assert "X-JSR-Bridge" in payload["error"]


def test_post_rejects_disallowed_origin(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/refresh",
        body={},
        headers={"X-JSR-Bridge": "1", "Origin": "https://evil.example.com"},
    )
    assert status == 403
    assert payload["error"] == "origin not allowed"


def test_post_rejects_malformed_json(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/refresh",
        raw="{not json",
        headers={"X-JSR-Bridge": "1", "Origin": "http://localhost:3000"},
    )
    assert status == 400


def test_post_rejects_non_object_json(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/refresh",
        raw="[1, 2, 3]",
        headers={"X-JSR-Bridge": "1"},
    )
    assert status == 400
    assert "object" in payload["error"]


def test_unknown_post_endpoint_is_404(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/nope", body={}, headers={"X-JSR-Bridge": "1"}
    )
    assert status == 404
    assert payload["error"] == "unknown endpoint"


# --------------------------------------------------------------------------
# /api/refresh
# --------------------------------------------------------------------------
def test_refresh_runs_once(run_server, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_once(config_path, **kwargs):
        captured["config_path"] = config_path
        captured["kwargs"] = kwargs
        return FakeSummary(scanned=7, new=2)

    monkeypatch.setattr(bridge, "run_once", fake_run_once)

    server = run_server(config_path=Path("/tmp/cfg.toml"))
    status, payload = server.post(
        "/api/refresh",
        body={"max_pages": 2, "no_enrich": True, "no_notify": True},
        headers={"X-JSR-Bridge": "1", "Origin": "http://localhost:5173"},
    )

    assert status == 200
    assert payload == {"ok": True, "summary": {"scanned": 7, "new": 2}}
    assert captured["config_path"] == Path("/tmp/cfg.toml")
    assert captured["kwargs"]["max_pages"] == 2
    assert captured["kwargs"]["no_enrich"] is True
    assert captured["kwargs"]["no_notify"] is True


def test_refresh_lock_conflict(run_server, monkeypatch) -> None:
    monkeypatch.setattr(bridge, "run_once", lambda *a, **k: FakeSummary())
    server = run_server()
    # Simulate an in-progress refresh by pre-acquiring the shared lock.
    server.server.state.refresh_lock.acquire()
    try:
        status, payload = server.post(
            "/api/refresh", body={}, headers={"X-JSR-Bridge": "1"}
        )
    finally:
        server.server.state.refresh_lock.release()
    assert status == 409
    assert "already running" in payload["error"]


def test_refresh_error_is_internal_server_error(run_server, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(bridge, "run_once", boom)
    server = run_server()
    status, payload = server.post("/api/refresh", body={}, headers={"X-JSR-Bridge": "1"})
    assert status == 500
    assert payload["error"] == "network down"


# --------------------------------------------------------------------------
# /api/telegram
# --------------------------------------------------------------------------
def test_telegram_validates_required_fields(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/telegram", body={"token": "t"}, headers={"X-JSR-Bridge": "1"}
    )
    assert status == 400
    assert "required" in payload["error"]


def test_telegram_relays_to_api(run_server, monkeypatch) -> None:
    sent: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, ok: bool = True, status_code: int = 200):
            self._ok = ok
            self.status_code = status_code
            self.text = ""

        def json(self):
            return {"ok": self._ok, "description": "" if self._ok else "bad"}

    def fake_post(url, json=None, timeout=None, impersonate=None):
        sent.append({"url": url, "json": json})
        return FakeResponse()

    monkeypatch.setattr(bridge.requests, "post", fake_post)

    server = run_server()
    status, payload = server.post(
        "/api/telegram",
        body={
            "token": "123:abc",
            "chat_ids": ["11", "22"],
            "text": "<b>hi</b>",
            "topic_id": "5",
        },
        headers={"X-JSR-Bridge": "1"},
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["delivered"] == ["11", "22"]
    assert payload["errors"] == []
    assert len(sent) == 2
    assert sent[0]["url"].endswith("/bot123:abc/sendMessage")
    assert sent[0]["json"]["message_thread_id"] == 5


def test_telegram_reports_per_chat_errors(run_server, monkeypatch) -> None:
    class FakeResponse:
        status_code = 400
        text = "Boom"

        def json(self):
            return {"ok": False, "description": "chat not found"}

    monkeypatch.setattr(
        bridge.requests, "post", lambda url, **kw: FakeResponse()
    )

    server = run_server()
    status, payload = server.post(
        "/api/telegram",
        body={"token": "t", "chat_ids": ["x"], "text": "hi"},
        headers={"X-JSR-Bridge": "1"},
    )

    assert status == 502
    assert payload["ok"] is False
    assert payload["delivered"] == []
    assert payload["errors"][0]["chat_id"] == "x"
    assert payload["errors"][0]["error"] == "chat not found"


def test_telegram_rejects_non_numeric_topic(run_server) -> None:
    server = run_server()
    status, payload = server.post(
        "/api/telegram",
        body={"token": "t", "chat_ids": ["x"], "text": "hi", "topic_id": "not-a-number"},
        headers={"X-JSR-Bridge": "1"},
    )
    # No chat actually delivered, so the run is a bad gateway with an error entry.
    assert status == 502
    assert payload["errors"] == [{"chat_id": "x", "error": "topic id must be a number"}]


# --------------------------------------------------------------------------
# Static file serving
# --------------------------------------------------------------------------
def test_static_blocks_path_traversal(run_server, tmp_path) -> None:
    static = tmp_path / "dist"
    static.mkdir()
    (static / "secret.txt").write_text("nope", encoding="utf-8")
    server = run_server(static_dir=static)
    # Request a path that escapes the static root after normalization.
    status, _payload = server.get("/jobstreetracer/../secret.txt")
    # urllib normalizes '..' in the request path; assert either a refusal or
    # the SPA fallback (never the secret file contents).
    assert status in (200, 403, 404)
    text_response = server.get("/jobstreetracer/..%2Fsecret.txt")
    assert text_response[0] in (200, 403, 404)
    if text_response[1] and isinstance(text_response[1], str):
        assert "nope" not in text_response[1]


def test_static_serves_file_and_falls_back_to_index(run_server, tmp_path) -> None:
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    server = run_server(static_dir=static)

    status, payload = server.get("/jobstreetracer/app.js")
    assert status == 200
    assert payload == "console.log(1)"

    # Unknown route without an extension falls back to index.html (SPA).
    status, payload = server.get("/jobstreetracer/deep/route")
    assert status == 200
    assert "index" in payload


def test_static_without_dir_configured_is_404(run_server) -> None:
    server = run_server(static_dir=None)
    status, payload = server.get("/jobstreetracer/")
    assert status == 404
    assert payload["error"] == "static dir not configured"


# --------------------------------------------------------------------------
# _origin_allowed unit checks
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        (None, True),
        ("", True),
        ("https://brrrassica.github.io", True),
        ("http://localhost:5173", True),
        ("http://127.0.0.1:8765", True),
        ("http://[::1]:3000", True),
        ("https://evil.example.com", False),
        ("http://evil.example.com", False),
    ],
)
def test_origin_allowed(origin: str | None, expected: bool) -> None:
    assert bridge._origin_allowed(origin) is expected
