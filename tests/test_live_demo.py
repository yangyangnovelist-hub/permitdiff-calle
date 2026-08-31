import argparse
import json
from pathlib import Path

import pytest

from permitdiff import live_demo


def args(tmp_path: Path):
    return argparse.Namespace(
        phone="+15555550123",
        region="US",
        locale="en-US",
        confirm_consent=live_demo.CONSENT_PHRASE,
        confirm_no_record_write=live_demo.NO_WRITE_PHRASE,
        timeout_seconds=5,
        base_url="http://127.0.0.1:8123",
        database=tmp_path / "ledger.sqlite3",
        public_output=tmp_path / "proof.json",
        failure_output=tmp_path / "failure.json",
    )


def successful_result():
    return {
        "call_id": "call-live-001",
        "status": "completed",
        "task_completed": True,
        "completion_confidence": {"score": 0.96},
        "structured_result": {"phone_status": "correction_required"},
        "decision": {
            "route": "discrepancy_detected",
            "official_status_mutated": False,
            "next_authority": "human_review",
        },
    }


def test_public_proof_is_privacy_safe_and_non_authoritative():
    proof = live_demo.public_proof(successful_result())
    assert proof["route"] == "discrepancy_detected"
    assert proof["decision"]["official_status_mutated"] is False
    assert "+15555550123" not in json.dumps(proof)


def test_public_proof_rejects_wrong_route_authority_and_shape():
    value = successful_result()
    value["decision"]["route"] = "verified_match"
    with pytest.raises(ValueError, match="discrepancy"):
        live_demo.public_proof(value)
    value = successful_result()
    value["decision"]["official_status_mutated"] = True
    with pytest.raises(ValueError, match="mutated=false"):
        live_demo.public_proof(value)
    value = successful_result()
    value["structured_result"] = None
    with pytest.raises(ValueError, match="structured"):
        live_demo.public_proof(value)


def test_live_demo_gates_and_writes_success_or_local_failure(tmp_path, monkeypatch):
    value = args(tmp_path)
    value.confirm_consent = "yes"
    with pytest.raises(ValueError, match="EXPLICIT CONSENT"):
        live_demo.run(value)
    value = args(tmp_path)
    value.confirm_no_record_write = "yes"
    with pytest.raises(ValueError, match="WILL NOT ALTER"):
        live_demo.run(value)
    value = args(tmp_path)
    value.timeout_seconds = 0
    with pytest.raises(ValueError, match="positive"):
        live_demo.run(value)
    value = args(tmp_path)
    value.public_output.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        live_demo.run(value)

    success_args = args(tmp_path / "success")
    monkeypatch.setattr(live_demo, "execute_once", lambda case, execute_args: successful_result())
    assert live_demo.run(success_args)["call_id"] == "call-live-001"
    assert json.loads(success_args.public_output.read_text())["route"] == "discrepancy_detected"

    failure_args = args(tmp_path / "failure")
    failed = successful_result()
    failed["decision"]["route"] = "outcome_unknown"
    monkeypatch.setattr(live_demo, "execute_once", lambda case, execute_args: failed)
    with pytest.raises(RuntimeError, match="do not retry"):
        live_demo.run(failure_args)
    failure = json.loads(failure_args.failure_output.read_text())
    assert failure["decision"]["route"] == "outcome_unknown"


def test_parse_args_and_main(tmp_path, monkeypatch, capsys):
    parsed = live_demo.parse_args(
        [
            "--phone",
            "+442079460123",
            "--region",
            "GB",
            "--locale",
            "en-GB",
            "--confirm-consent",
            live_demo.CONSENT_PHRASE,
            "--confirm-no-record-write",
            live_demo.NO_WRITE_PHRASE,
        ]
    )
    assert parsed.region == "GB" and parsed.locale == "en-GB"
    monkeypatch.setattr(live_demo, "run", lambda value: {"call_id": "call-main-001"})
    assert (
        live_demo.main(
            [
                "--phone",
                "+15555550123",
                "--confirm-consent",
                live_demo.CONSENT_PHRASE,
                "--confirm-no-record-write",
                live_demo.NO_WRITE_PHRASE,
                "--public-output",
                str(tmp_path / "proof.json"),
            ]
        )
        == 0
    )
    assert "call-main-001" in capsys.readouterr().out
