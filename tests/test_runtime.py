import pytest

from permitdiff.models import parse_request
from permitdiff.runtime import DEFAULT_BASE_URL, execute, validate_base_url
from tests.test_policy import RAW, provider


class Calls:
    def __init__(self, case, *, call_id="call-001", result=None):
        self.case = case
        self.call_id = call_id
        self.result = result if result is not None else provider(case)
        self.created = None

    def create(self, **kwargs):
        self.created = kwargs
        return {"id": self.call_id}

    def wait_for_result(self, call_id, *, timeout_seconds, interval_seconds):
        assert call_id == self.call_id
        assert timeout_seconds == 9
        assert interval_seconds == 2
        return self.result


def test_execute_calls_sdk_and_routes_bound_result():
    case = parse_request(RAW)
    calls = Calls(case)
    accepted = []
    result = execute(case, calls, 9, accepted.append)
    assert accepted == ["call-001"]
    assert calls.created["idempotency_key"].startswith("permitdiff-")
    assert result["decision"]["route"] == "discrepancy_detected"


def test_execute_rejects_missing_id_and_non_object_result():
    case = parse_request(RAW)
    with pytest.raises(RuntimeError, match="call id"):
        execute(case, Calls(case, call_id=""), 9)
    with pytest.raises(RuntimeError, match="not an object"):
        execute(case, Calls(case, result={**provider(case), "structured_result": "bad"}), 9)


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example",
        "http://api.heycall-e.com",
        "https://user:pass@api.heycall-e.com",
        "https://api.heycall-e.com/path",
        "http://localhost",
    ],
)
def test_base_url_rejects_untrusted_origins(value):
    with pytest.raises(ValueError, match="official HTTPS"):
        validate_base_url(value)


def test_base_url_allows_official_and_explicit_loopback():
    assert validate_base_url("https://api.heycall-e.com/") == DEFAULT_BASE_URL
    assert validate_base_url("http://127.0.0.1:8123/") == "http://127.0.0.1:8123"
