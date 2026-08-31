"""Run one consented synthetic permit discrepancy call and emit public-safe proof."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from permitdiff.cli import execute_once
from permitdiff.models import parse_request
from permitdiff.runtime import DEFAULT_BASE_URL

CONSENT_PHRASE = "I HAVE EXPLICIT CONSENT"
NO_WRITE_PHRASE = "PHONE EVIDENCE WILL NOT ALTER THE RECORD"
DEFAULT_DATABASE = Path("data/consented-live-demo.sqlite3")
DEFAULT_FAILURE_OUTPUT = Path("data/consented-live-last-result.json")
DEFAULT_PUBLIC_OUTPUT = Path("artifacts/consented-live-discrepancy.json")


def synthetic_request(phone: str, region: str = "US", locale: str = "en-US") -> dict[str, Any]:
    return {
        "case_id": "case-BL-2026-1842",
        "permit_number": "BL-2026-1842",
        "jurisdiction": "Example City",
        "agency_name": "Example City Permit Office",
        "agency_phone": phone,
        "authorized_agency_contact": True,
        "applicant_business_name": "Acme Construction",
        "portal_status": "in_review",
        "portal_updated_at_utc": "2026-08-25T08:00:00Z",
        "checked_at_utc": "2026-08-30T08:00:00Z",
        "portal_note": "Plan review is still in progress with no missing items shown.",
        "freshness_window_hours": 48,
        "conflict_flags": [],
        "region": region,
        "locale": locale,
    }


def public_proof(result: dict[str, Any]) -> dict[str, Any]:
    decision = result.get("decision")
    structured = result.get("structured_result")
    if not isinstance(decision, dict) or decision.get("route") != "discrepancy_detected":
        raise ValueError("public proof requires a real discrepancy_detected route")
    if decision.get("official_status_mutated") is not False:
        raise ValueError("public proof requires official_status_mutated=false")
    if not isinstance(structured, dict):
        raise ValueError("public proof requires a structured result")
    return {
        "evidence_type": "consented_live_discrepancy_synthetic_permit_case",
        "provider": "CALL-E",
        "call_id": result.get("call_id"),
        "status": result.get("status"),
        "task_completed": result.get("task_completed"),
        "completion_confidence": result.get("completion_confidence"),
        "route": "discrepancy_detected",
        "decision": decision,
        "privacy": {
            "real_phone_number_published": False,
            "participant_identity_published": False,
            "transcript_published": False,
            "recording_published": False,
        },
        "claim_boundary": (
            "Real CALL-E transport and PermitDiff discrepancy routing in a synthetic permit case; "
            "the phone answer did not alter an official record."
        ),
    }


def write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_replace(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phone", required=True, help="Owned or explicitly authorized E.164 number"
    )
    parser.add_argument("--region", default="US")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--confirm-consent", required=True)
    parser.add_argument("--confirm-no-record-write", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--base-url", default=os.environ.get("CALLE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_OUTPUT)
    parser.add_argument("--failure-output", type=Path, default=DEFAULT_FAILURE_OUTPUT)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm_consent != CONSENT_PHRASE:
        raise ValueError(f"--confirm-consent must equal: {CONSENT_PHRASE}")
    if args.confirm_no_record_write != NO_WRITE_PHRASE:
        raise ValueError(f"--confirm-no-record-write must equal: {NO_WRITE_PHRASE}")
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.public_output.exists():
        raise ValueError(f"refusing to overwrite existing public proof: {args.public_output}")
    case = parse_request(synthetic_request(args.phone, args.region, args.locale))
    execute_args = argparse.Namespace(
        confirm_authorized_recipient=True,
        confirm_no_record_write=True,
        allow=[args.phone],
        timeout_seconds=args.timeout_seconds,
        base_url=args.base_url,
        database=args.database,
    )
    result = execute_once(case, execute_args)
    if result.get("decision", {}).get("route") != "discrepancy_detected":
        write_replace(args.failure_output, result)
        raise RuntimeError(
            "CALL-E completed without a discrepancy; inspect the local result and do not retry"
        )
    proof = public_proof(result)
    write_exclusive(args.public_output, proof)
    return proof


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        proof = run(args)
        sys.stdout.write(
            f"Consented discrepancy proof created: {args.public_output}\n"
            f"call_id={proof.get('call_id')}\n"
        )
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
