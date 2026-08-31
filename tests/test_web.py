import argparse
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from permitdiff import web
from tests.test_policy import RAW, fresh_raw


def start_server(tmp_path: Path, *, live=False):
    config = web.WebConfig(
        allow=(RAW["agency_phone"],) if live else (),
        enable_live_ui=live,
        timeout_seconds=5,
        base_url="http://127.0.0.1:8123",
        database=tmp_path / "web.sqlite3",
    )
    server = web.OperatorServer(("127.0.0.1", 0), config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def fetch(url, *, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode()


def test_operator_surface_and_capabilities(tmp_path):
    server, thread, base = start_server(tmp_path)
    try:
        status, headers, body = fetch(base + "/")
        assert status == 200
        assert "Call only when the record needs reconciliation" in body
        assert headers["Content-Security-Policy"]
        status, _, body = fetch(base + "/api/capabilities")
        assert status == 200
        assert json.loads(body)["phone_can_mutate_official_record"] is False
        assert fetch(base + "/missing")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_policy_preview_and_simulation_routes(tmp_path):
    server, thread, base = start_server(tmp_path)
    headers = {"Content-Type": "application/json"}
    try:
        status, _, body = fetch(
            base + "/api/preview", payload={"request": fresh_raw()}, headers=headers
        )
        assert status == 200
        assert json.loads(body)["route"] == "no_call_needed"
        status, _, body = fetch(base + "/api/preview", payload={"request": RAW}, headers=headers)
        assert status == 200
        assert json.loads(body)["call_reason"] == "stale_portal_record"
        for scenario, expected in [
            ("verified-match", "verified_match"),
            ("discrepancy", "discrepancy_detected"),
            ("unknown", "outcome_unknown"),
            ("voicemail", "outcome_unknown"),
        ]:
            status, _, body = fetch(
                base + "/api/simulate",
                payload={"request": RAW, "scenario": scenario},
                headers=headers,
            )
            assert status == 200
            assert json.loads(body)["decision"]["route"] == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_web_rejects_bad_requests_and_disabled_live(tmp_path):
    server, thread, base = start_server(tmp_path)
    try:
        assert fetch(base + "/api/preview", payload={"request": RAW})[0] == 400
        status, _, body = fetch(
            base + "/api/simulate",
            payload={"request": RAW, "scenario": "wishful"},
            headers={"Content-Type": "application/json"},
        )
        assert status == 400 and "unsupported" in body
        status, _, body = fetch(
            base + "/api/execute",
            payload={"request": RAW},
            headers={"Content-Type": "application/json"},
        )
        assert status == 400 and "disabled" in body
        assert (
            fetch(
                base + "/api/not-a-route",
                payload={"request": RAW},
                headers={"Content-Type": "application/json"},
            )[0]
            == 404
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_live_ui_requires_every_gate_and_exact_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(
        web,
        "execute_once",
        lambda case, args: {"decision": {"route": "discrepancy_detected"}},
    )
    server, thread, base = start_server(tmp_path, live=True)
    headers = {"Content-Type": "application/json"}
    payload = {"request": RAW}
    try:
        status, _, body = fetch(base + "/api/execute", payload=payload, headers=headers)
        assert status == 400 and "authorization" in body
        payload["confirm_authorized_recipient"] = True
        status, _, body = fetch(base + "/api/execute", payload=payload, headers=headers)
        assert status == 400 and web.CONFIRM_PHRASE in body
        payload["confirm_phrase"] = web.CONFIRM_PHRASE
        status, _, body = fetch(base + "/api/execute", payload=payload, headers=headers)
        assert status == 400 and web.NO_WRITE_PHRASE in body
        payload["confirm_no_write_phrase"] = web.NO_WRITE_PHRASE
        status, _, body = fetch(base + "/api/execute", payload=payload, headers=headers)
        assert status == 200
        assert json.loads(body)["decision"]["route"] == "discrepancy_detected"
        wrong = json.loads(json.dumps(payload))
        wrong["request"]["agency_phone"] = "+15555550999"
        status, _, body = fetch(base + "/api/execute", payload=wrong, headers=headers)
        assert status == 400 and "allowlist" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def namespace(tmp_path, **changes):
    value = argparse.Namespace(
        host="127.0.0.1",
        port=0,
        allow=[],
        enable_live_ui=False,
        timeout_seconds=5,
        base_url="https://api.heycall-e.com",
        database=tmp_path / "web.sqlite3",
    )
    for key, item in changes.items():
        setattr(value, key, item)
    return value


def test_server_builder_enforces_loopback_port_timeout_and_allowlist(tmp_path):
    server = web.build_server(namespace(tmp_path))
    server.server_close()
    for changes, message in [
        ({"port": 70000}, "port"),
        ({"timeout_seconds": 0}, "positive"),
        ({"enable_live_ui": True}, "allow"),
        (
            {"enable_live_ui": True, "allow": [RAW["agency_phone"]], "host": "0.0.0.0"},
            "loopback",
        ),
    ]:
        with pytest.raises(ValueError, match=message):
            web.build_server(namespace(tmp_path, **changes))
    assert web.is_loopback_host("localhost")
    assert web.is_loopback_host("::1")
    assert not web.is_loopback_host("example.com")
