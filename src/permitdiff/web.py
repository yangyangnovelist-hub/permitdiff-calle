"""Loopback operator console for exception-first permit reconciliation."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from permitdiff.cli import execute_once
from permitdiff.live_demo import synthetic_request
from permitdiff.models import PermitCase, parse_request
from permitdiff.policy import preview, simulated_result
from permitdiff.runtime import DEFAULT_BASE_URL

MAX_BODY_BYTES = 64 * 1024
CONFIRM_PHRASE = "CALL AUTHORIZED"
NO_WRITE_PHRASE = "PHONE EVIDENCE WILL NOT ALTER THE RECORD"
HTML_PATH = Path(__file__).with_name("operator.html")
EXAMPLE_REQUEST = synthetic_request("+15555550100")


def operator_html() -> str:
    return HTML_PATH.read_text(encoding="utf-8").replace(
        "__EXAMPLE__", json.dumps(EXAMPLE_REQUEST)
    )


@dataclass(frozen=True)
class WebConfig:
    allow: tuple[str, ...] = ()
    enable_live_ui: bool = False
    timeout_seconds: int = 600
    base_url: str = DEFAULT_BASE_URL
    database: Path = Path("data/permitdiff-web.sqlite3")

    def capabilities(self) -> dict[str, Any]:
        return {
            "live_ui_enabled": self.enable_live_ui,
            "allowlist_count": len(self.allow),
            "live_environment_ready": (
                os.environ.get("CALLE_LIVE_CALLS_ENABLED", "").lower() == "true"
                and bool(os.environ.get("CALLE_API_KEY"))
            ),
            "phone_can_mutate_official_record": False,
        }


class OperatorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: WebConfig):
        self.config = config
        super().__init__(address, OperatorHandler)


class OperatorHandler(BaseHTTPRequestHandler):
    server: OperatorServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("permitdiff-web: " + (format % args) + "\n")

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _html(self) -> None:
        data = operator_html().encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    def _payload(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body must be between 1 byte and 64 KiB")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    @staticmethod
    def _request(payload: dict[str, Any]) -> PermitCase:
        raw = payload.get("request")
        if not isinstance(raw, dict):
            raise ValueError("request must be a JSON object")
        return parse_request(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._html()
        elif self.path == "/api/capabilities":
            self._json(HTTPStatus.OK, self.server.config.capabilities())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._payload()
            case = self._request(payload)
            if self.path == "/api/preview":
                result = preview(case)
            elif self.path == "/api/simulate":
                scenario = payload.get("scenario", "discrepancy")
                if scenario not in {"verified-match", "discrepancy", "unknown", "voicemail"}:
                    raise ValueError("unsupported simulation scenario")
                result = simulated_result(case, scenario)
            elif self.path == "/api/execute":
                result = self._execute(case, payload)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._json(HTTPStatus.OK, result)
        except json.JSONDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except OSError as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(exc).__name__})

    def _execute(self, case: PermitCase, payload: dict[str, Any]) -> dict[str, Any]:
        config = self.server.config
        host = urlsplit(f"//{self.headers.get('Host', '')}").hostname or ""
        if not is_loopback_host(host):
            raise ValueError("live execution requires a loopback Host header")
        if not config.enable_live_ui:
            raise ValueError("live execution is disabled on this operator server")
        if payload.get("confirm_authorized_recipient") is not True:
            raise ValueError("live execution requires recipient authorization confirmation")
        if payload.get("confirm_phrase") != CONFIRM_PHRASE:
            raise ValueError(f"live execution requires typing {CONFIRM_PHRASE}")
        if payload.get("confirm_no_write_phrase") != NO_WRITE_PHRASE:
            raise ValueError(f"live execution requires typing {NO_WRITE_PHRASE}")
        if case.agency_phone not in config.allow:
            raise ValueError("destination is not in the server-side exact-number allowlist")
        args = argparse.Namespace(
            confirm_authorized_recipient=True,
            confirm_no_record_write=True,
            allow=list(config.allow),
            timeout_seconds=config.timeout_seconds,
            base_url=config.base_url,
            database=config.database,
        )
        return execute_once(case, args)


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--allow", action="append", default=[])
    parser.add_argument("--enable-live-ui", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--base-url", default=os.environ.get("CALLE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("PERMITDIFF_WEB_DB_PATH", "data/permitdiff-web.sqlite3")),
    )
    return parser.parse_args(argv)


def build_server(args: argparse.Namespace) -> OperatorServer:
    if args.port < 0 or args.port > 65535:
        raise ValueError("port must be between 0 and 65535")
    if args.timeout_seconds <= 0:
        raise ValueError("timeout-seconds must be positive")
    if args.enable_live_ui and not is_loopback_host(args.host):
        raise ValueError("live operator UI may only bind to a loopback host")
    if args.enable_live_ui and not args.allow:
        raise ValueError("live operator UI requires at least one exact --allow destination")
    return OperatorServer(
        (args.host, args.port),
        WebConfig(
            allow=tuple(dict.fromkeys(args.allow)),
            enable_live_ui=args.enable_live_ui,
            timeout_seconds=args.timeout_seconds,
            base_url=args.base_url,
            database=args.database,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        server = build_server(parse_args(argv))
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    host, port = server.server_address[:2]
    sys.stdout.write(f"PermitDiff reconciliation console: http://{host}:{port}/\n")
    if not server.config.enable_live_ui:
        sys.stdout.write("Live execution is disabled; policy and deterministic routes only.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
