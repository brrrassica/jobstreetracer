"""Tiny localhost bridge for the JobStreetracer PWA.

The PWA is hosted as a static GitHub Pages app. Browsers cannot scrape JobStreet
(Cloudflare, CORS) or read the local SQLite file, so this optional companion
exposes the existing CLI state on ``127.0.0.1``:

* ``GET  /api/feed``      -> the same JSON feed as ``jobstreetracer publish``
* ``POST /api/refresh``   -> run one scrape cycle now
* ``POST /api/telegram``  -> relay a Telegram send (avoids browser CORS)
* ``GET  /api/health``    -> liveness/version probe

It is deliberately not a daemon: run it on demand, or add it to your desktop
autostart so the installed PWA can keep working while you are logged in.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from curl_cffi import requests

from . import __version__
from .config import ConfigError, load_config
from .publish import build_feed
from .runner import run_once

log = logging.getLogger(__name__)

DEFAULT_PORT = 8765
MAX_BODY_BYTES = 256 * 1024
TELEGRAM_API = "https://api.telegram.org"


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True  # non-browser clients (curl) have no Origin header
    if origin == "https://brrrassica.github.io":
        return True
    return origin.startswith(("http://localhost:", "http://127.0.0.1:", "http://[::1]:"))


@dataclass
class BridgeState:
    config_path: Path | None
    static_dir: Path | None
    refresh_lock: threading.Lock = field(default_factory=threading.Lock)


class BridgeHandler(SimpleHTTPRequestHandler):
    server_version = f"JobStreetracerBridge/{__version__}"

    # -- helpers -------------------------------------------------------
    @property
    def state(self) -> BridgeState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        log.info("%s - %s", self.address_string(), fmt % args)

    def end_headers(self) -> None:
        origin = self.headers.get("Origin")
        if _origin_allowed(origin) and origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, X-JSR-Bridge"
        )
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    # -- HTTP verbs ----------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "version": __version__})
            return
        if path == "/api/feed":
            self._serve_feed()
            return
        if path in ("/", "/jobstreetracer"):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/jobstreetracer/")
            self.end_headers()
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get("X-JSR-Bridge") != "1":
            self._json(
                HTTPStatus.FORBIDDEN,
                {"error": "missing X-JSR-Bridge header"},
            )
            return
        origin = self.headers.get("Origin")
        if not _origin_allowed(origin):
            self._json(HTTPStatus.FORBIDDEN, {"error": "origin not allowed"})
            return
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if path == "/api/refresh":
            self._refresh(body)
        elif path == "/api/telegram":
            self._telegram(body)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})

    # -- route implementations ----------------------------------------
    def _serve_feed(self) -> None:
        try:
            config = load_config(self.state.config_path)
            feed = build_feed(config)
        except ConfigError as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            return
        except Exception as exc:
            log.exception("feed build failed")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, feed)

    def _refresh(self, body: dict[str, Any]) -> None:
        if not self.state.refresh_lock.acquire(blocking=False):
            self._json(
                HTTPStatus.CONFLICT,
                {"error": "a refresh is already running"},
            )
            return
        try:
            summary = run_once(
                self.state.config_path,
                search_names=body.get("search") or None,
                max_pages=body.get("max_pages"),
                no_enrich=bool(body.get("no_enrich")),
                no_notify=bool(body.get("no_notify")),
            )
        except Exception as exc:
            log.exception("refresh failed")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        finally:
            self.state.refresh_lock.release()
        self._json(HTTPStatus.OK, {"ok": True, "summary": summary.to_dict()})

    def _telegram(self, body: dict[str, Any]) -> None:
        token = str(body.get("token") or "").strip()
        chat_ids = body.get("chat_ids") or []
        text = str(body.get("text") or "")
        topic_id = str(body.get("topic_id") or "").strip()
        if isinstance(chat_ids, str):
            chat_ids = [chat_ids]
        chat_ids = [str(item).strip() for item in chat_ids if str(item).strip()]
        if not token or not chat_ids or not text:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"error": "token, chat_ids and text are required"},
            )
            return
        delivered: list[str] = []
        errors: list[dict[str, str]] = []
        for chat_id in chat_ids:
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if topic_id:
                try:
                    payload["message_thread_id"] = int(topic_id)
                except ValueError:
                    errors.append({"chat_id": chat_id, "error": "topic id must be a number"})
                    continue
            try:
                response = requests.post(
                    f"{TELEGRAM_API}/bot{token}/sendMessage",
                    json=payload,
                    timeout=20,
                    impersonate="chrome",
                )
                data = response.json()
                if response.status_code >= 400 or not data.get("ok"):
                    errors.append(
                        {
                            "chat_id": chat_id,
                            "error": str(data.get("description") or response.text[:200]),
                        }
                    )
                else:
                    delivered.append(chat_id)
            except Exception as exc:
                errors.append({"chat_id": chat_id, "error": str(exc)})
        status = HTTPStatus.OK if delivered else HTTPStatus.BAD_GATEWAY
        self._json(status, {"ok": bool(delivered), "delivered": delivered, "errors": errors})

    # -- static files --------------------------------------------------
    def _serve_static(self, path: str) -> None:
        static = self.state.static_dir
        if static is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "static dir not configured"})
            return
        prefix = "/jobstreetracer/"
        if not path.startswith(prefix):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        relative = unquote(path[len(prefix) :]) or "index.html"
        candidate = (static / relative).resolve()
        try:
            candidate.relative_to(static.resolve())
        except ValueError:
            self._json(HTTPStatus.FORBIDDEN, {"error": "invalid path"})
            return
        if not candidate.is_file():
            candidate = static / "index.html"  # SPA fallback
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "build the PWA first"})
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    state: BridgeState

    def __init__(self, address: tuple[str, int], state: BridgeState) -> None:
        self.state = state
        super().__init__(address, BridgeHandler)


def serve_bridge(
    config_path: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    static_dir: str | Path | None = None,
    open_browser: bool = False,
) -> None:
    state = BridgeState(
        config_path=Path(config_path).expanduser().resolve() if config_path else None,
        static_dir=Path(static_dir).expanduser().resolve() if static_dir else None,
    )
    server = BridgeServer((host, port), state)
    base = f"http://{host}:{server.server_address[1]}"
    url = f"{base}/jobstreetracer/"
    log.info("bridge listening on %s", base)
    print(f"JobStreetracer bridge: {base}")
    print(f"Feed endpoint: {base}/api/feed")
    if static_dir:
        print(f"PWA: {url}")
    else:
        print("PWA: https://brrrassica.github.io/jobstreetracer/ (no --static directory)")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url if static_dir else "https://brrrassica.github.io/jobstreetracer/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("bridge stopped")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local JobStreetracer PWA bridge.")
    parser.add_argument("--config", "-c", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--static", default=None, help="built PWA directory (web/dist)")
    parser.add_argument("--open", action="store_true", help="open the PWA in a browser")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    serve_bridge(
        args.config,
        host=args.host,
        port=args.port,
        static_dir=args.static,
        open_browser=args.open,
    )


if __name__ == "__main__":
    main()
