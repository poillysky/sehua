"""独立线程紧急停止：主事件循环被爬虫堵住时，仍可经旁路端口停爬。"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

log = logging.getLogger(__name__)

_DEFAULT_PORT = 18080
_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_stop_fn: Callable[[], dict] | None = None


def _cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.debug("emergency-stop: " + fmt, *args)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        path = (self.path or "").split("?", 1)[0]
        if path not in {"/stop", "/api/crawler/emergency-stop"}:
            self.send_response(404)
            _cors(self)
            self.end_headers()
            return
        payload = b'{"ok":false,"message":"no handler"}'
        code = 500
        try:
            if _stop_fn is None:
                raise RuntimeError("紧急停止未绑定")
            result = _stop_fn()
            import json

            payload = json.dumps(
                {"ok": True, "message": "紧急停止已执行", **(result or {})},
                ensure_ascii=False,
            ).encode("utf-8")
            code = 200
        except Exception as exc:
            log.warning("emergency stop failed: %s", exc)
            import json

            payload = json.dumps(
                {"ok": False, "message": str(exc)},
                ensure_ascii=False,
            ).encode("utf-8")
            code = 500
        self.send_response(code)
        _cors(self)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if (self.path or "").split("?", 1)[0] == "/health":
            body = b'{"ok":true,"service":"emergency-stop"}'
            self.send_response(200)
            _cors(self)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        _cors(self)
        self.end_headers()


def start_emergency_stop_server(
    stop_fn: Callable[[], dict],
    *,
    port: int = _DEFAULT_PORT,
) -> int:
    """启动旁路停止服务；返回实际端口（失败返回 0）。"""
    global _server, _thread, _stop_fn
    if _server is not None:
        _stop_fn = stop_fn
        return int(_server.server_address[1])

    _stop_fn = stop_fn
    try:
        server = ThreadingHTTPServer(("127.0.0.1", int(port)), _Handler)
    except OSError as exc:
        log.warning("emergency stop server bind %s failed: %s", port, exc)
        return 0

    _server = server

    def _run() -> None:
        log.info("emergency stop listening on http://127.0.0.1:%s/stop", server.server_address[1])
        try:
            server.serve_forever(poll_interval=0.3)
        except Exception as exc:
            log.warning("emergency stop server stopped: %s", exc)

    _thread = threading.Thread(target=_run, name="emergency-stop", daemon=True)
    _thread.start()
    return int(server.server_address[1])


def stop_emergency_stop_server() -> None:
    global _server, _thread, _stop_fn
    srv = _server
    _server = None
    _stop_fn = None
    if srv is not None:
        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            srv.server_close()
        except Exception:
            pass
    _thread = None
