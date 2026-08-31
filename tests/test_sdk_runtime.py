"""Prove the published CALL-E SDK performs HTTP at runtime."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from calle import CalleClient

from permitdiff.models import parse_request
from permitdiff.policy import call_arguments, simulated_result
from permitdiff.runtime import execute
from tests.test_policy import RAW


class CaptureHandler(BaseHTTPRequestHandler):
    requests = []
    case = parse_request(RAW)

    def log_message(self, format, *args):
        return

    def send_payload(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(
            {
                "method": "POST",
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "idempotency_key": self.headers.get("Idempotency-Key"),
                "payload": payload,
            }
        )
        self.send_payload(201, {"id": "call_sdk_001", "status": "queued"})

    def do_GET(self):
        type(self).requests.append({"method": "GET", "path": self.path})
        case = type(self).case
        structured = simulated_result(case, "discrepancy")["structured_result"]
        self.send_payload(
            200,
            {
                "id": "call_sdk_001",
                "status": "completed",
                "task_completed": True,
                "completion_confidence": {"score": 0.96, "label": "high"},
                "structured_result": structured,
                "evidence": ["Recipient office evidence captured."],
                "metadata": call_arguments(case)["metadata"],
                "recipients": [
                    {
                        "phone": case.agency_phone,
                        "attempts": [
                            {
                                "transcript_turns": [
                                    {
                                        "speaker": "recipient",
                                        "text": f"Reference {structured['agency_reference']}.",
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
        )


def test_published_sdk_posts_and_polls_real_http():
    CaptureHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    case = parse_request(RAW)
    try:
        with CalleClient(
            api_key="calle_test_capture",
            base_url=f"http://127.0.0.1:{server.server_port}",
        ) as sdk:
            result = execute(case, sdk.calls, timeout_seconds=5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert [item["method"] for item in CaptureHandler.requests] == ["POST", "GET"]
    create = CaptureHandler.requests[0]
    assert create["path"] == "/v1/calls"
    assert create["authorization"] == "Bearer calle_test_capture"
    assert create["idempotency_key"].startswith("permitdiff-")
    assert create["payload"]["metadata"]["workflow_type"] == "permit_record_reconciliation"
    assert CaptureHandler.requests[1]["path"] == "/v1/calls/call_sdk_001"
    assert result["decision"]["route"] == "discrepancy_detected"
