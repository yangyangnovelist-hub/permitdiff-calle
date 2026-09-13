"""Exception-first call policy, strict schema, and non-authoritative reconciliation routing."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from permitdiff.models import PermitCase, age_hours

TERMINAL_SUCCESS = {"completed", "succeeded"}
MIN_CONFIDENCE = 0.8
RECIPIENT_SPEAKERS = {"recipient", "user", "callee"}
PHONE_LIKE = re.compile(r"(?<!\w)\+?[1-9]\d{7,14}(?!\w)")
EMAIL_LIKE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_LIKE = re.compile(
    r"(?i)\b(bearer|token|api[_ -]?key|access[_ -]?token|password|private[_ -]?key|"
    r"client[_ -]?secret|secret|credential)\b\s*[:=]?\s*\S+"
)


def result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "consented_after_ai_disclosure",
            "right_permit_office",
            "permit_reference_confirmed",
            "phone_status",
            "next_required_action",
            "missing_items_summary",
            "agency_reference",
            "evidence_summary",
        ],
        "properties": {
            "consented_after_ai_disclosure": {
                "type": "string",
                "enum": ["yes", "no", "unknown"],
            },
            "right_permit_office": {"type": "string", "enum": ["yes", "no", "unknown"]},
            "permit_reference_confirmed": {
                "type": "string",
                "enum": ["yes", "no", "unknown"],
            },
            "phone_status": {
                "type": "string",
                "enum": [
                    "received",
                    "in_review",
                    "correction_required",
                    "approved",
                    "denied",
                    "unknown",
                ],
            },
            "next_required_action": {"type": "string", "maxLength": 300},
            "missing_items_summary": {"type": "string", "maxLength": 300},
            "agency_reference": {"type": "string", "maxLength": 80},
            "evidence_summary": {"type": "string", "maxLength": 500},
        },
        "additionalProperties": False,
    }


def portal_snapshot(case: PermitCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "permit_number": case.permit_number,
        "jurisdiction": case.jurisdiction,
        "agency_name": case.agency_name,
        "applicant_business_name": case.applicant_business_name,
        "portal_status": case.portal_status,
        "portal_updated_at_utc": case.portal_updated_at_utc,
        "checked_at_utc": case.checked_at_utc,
        "portal_note": case.portal_note,
        "freshness_window_hours": case.freshness_window_hours,
        "conflict_flags": list(case.conflict_flags),
    }


def snapshot_hash(case: PermitCase) -> str:
    canonical = json.dumps(
        portal_snapshot(case), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def call_reason(case: PermitCase) -> str | None:
    if case.conflict_flags:
        return "conflicting_portal_evidence"
    if age_hours(case) > case.freshness_window_hours:
        return "stale_portal_record"
    return None


def build_task(case: PermitCase) -> str:
    return (
        f"Call the authorized public permit office {case.agency_name} in {case.jurisdiction} on "
        f"behalf of {case.applicant_business_name}. Speak in locale {case.locale}. Identify "
        "yourself as an AI calling assistant and ask whether this is the correct permit office and "
        "whether the recipient consents to continue. If either answer is not clearly yes, disclose "
        "no permit details and end the call. Never request or reveal credentials, authentication "
        "codes, personal data, payment data, inspection access codes, or contract terms. After "
        f"consent, reference permit {case.permit_number}. The frozen portal status is "
        f"{case.portal_status}; its non-sensitive note is: "
        f"{case.portal_note.rstrip('. ')}. Ask the "
        "office to confirm the permit reference, current status, next required applicant action, "
        "missing items if any, and an office reference for this answer. Read the facts back once. "
        "Do not request a status change, submit corrections, schedule an inspection, promise an "
        "outcome, or represent the phone answer as official permit truth."
    )


def call_arguments(case: PermitCase) -> dict[str, Any]:
    return {
        "task": build_task(case),
        "recipients": [
            {"phones": [case.agency_phone], "region": case.region, "locale": case.locale}
        ],
        "result_schema": result_schema(),
        "metadata": {
            "workflow_type": "permit_record_reconciliation",
            "case_id": case.case_id,
            "permit_number": case.permit_number,
            "snapshot_hash": snapshot_hash(case),
        },
    }


def idempotency_key(case: PermitCase) -> str:
    canonical = json.dumps(
        call_arguments(case), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return f"permitdiff-{hashlib.sha256(canonical).hexdigest()}"


def confidence_score(value: Any) -> float:
    """Accept only a finite probability; malformed confidence must fail closed."""
    if isinstance(value, dict):
        value = value.get("score")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        return 0.0
    return float(value)


def valid_result(value: Any) -> bool:
    schema = result_schema()
    if not isinstance(value, dict) or set(value) != set(schema["required"]):
        return False
    for field, rule in schema["properties"].items():
        item = value[field]
        if not isinstance(item, str) or len(item) > rule.get("maxLength", 10_000):
            return False
        if "enum" in rule and item not in rule["enum"]:
            return False
    return value["phone_status"] == "unknown" or len(value["agency_reference"].strip()) >= 3


def _recipient_transcript(provider_result: dict[str, Any], destination: str) -> str:
    recipients = provider_result.get("recipients")
    if not isinstance(recipients, list) or len(recipients) != 1:
        return ""
    recipient = recipients[0]
    if not isinstance(recipient, dict) or recipient.get("phone") != destination:
        return ""
    turns: list[str] = []
    for attempt in recipient.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        for turn in attempt.get("transcript_turns", []):
            if (
                isinstance(turn, dict)
                and str(turn.get("speaker", "")).lower() in RECIPIENT_SPEAKERS
                and isinstance(turn.get("text"), str)
            ):
                turns.append(turn["text"])
    return "\n".join(turns)


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.casefold())


def _reference_corroborated(reference: str, transcript: str) -> bool:
    expected = _tokens(reference)
    observed = _tokens(transcript)
    if not expected:
        return False
    width = len(expected)
    return any(
        observed[index : index + width] == expected
        for index in range(len(observed) - width + 1)
    )


def no_call_result(case: PermitCase) -> dict[str, Any]:
    return {
        "mode": "policy",
        "creates_phone_call": False,
        "route": "no_call_needed",
        "reason": "The portal snapshot is fresh and contains no declared conflict.",
        "portal_age_hours": age_hours(case),
        "official_status": case.portal_status,
        "official_status_mutated": False,
    }


def route_result(
    case: PermitCase,
    provider_result: dict[str, Any],
    *,
    expected_call_id: str | None = None,
) -> dict[str, Any]:
    unknown = {
        "route": "outcome_unknown",
        "official_status": case.portal_status,
        "official_status_mutated": False,
        "next_authority": "human_review",
    }
    if (
        provider_result.get("status") not in TERMINAL_SUCCESS
        or provider_result.get("task_completed") is not True
        or confidence_score(provider_result.get("completion_confidence")) < MIN_CONFIDENCE
    ):
        return {**unknown, "reason": "CALL-E did not return a reliable terminal success."}
    structured = provider_result.get("structured_result")
    if not valid_result(structured):
        return {**unknown, "reason": "CALL-E did not return the complete result schema."}
    assert isinstance(structured, dict)
    expected_metadata = {
        "workflow_type": "permit_record_reconciliation",
        "case_id": case.case_id,
        "permit_number": case.permit_number,
        "snapshot_hash": snapshot_hash(case),
    }
    transcript = _recipient_transcript(provider_result, case.agency_phone)
    evidence = provider_result.get("evidence")
    if (
        provider_result.get("metadata") != expected_metadata
        or (expected_call_id is not None and provider_result.get("id") != expected_call_id)
        or not isinstance(evidence, list)
        or not any(isinstance(item, str) and item.strip() for item in evidence)
        or not transcript
    ):
        return {**unknown, "reason": "Evidence was not bound to the approved portal snapshot."}
    if (
        structured["consented_after_ai_disclosure"] != "yes"
        or structured["right_permit_office"] != "yes"
        or structured["permit_reference_confirmed"] != "yes"
    ):
        return {**unknown, "reason": "Office consent or permit reference was not confirmed."}
    phone_status = structured["phone_status"]
    if phone_status == "unknown":
        return {**unknown, "reason": "The office did not provide a classifiable current status."}
    if not _reference_corroborated(structured["agency_reference"], transcript):
        return {**unknown, "reason": "The office reference was not corroborated by the recipient."}
    route = "verified_match" if phone_status == case.portal_status else "discrepancy_detected"
    return {
        "route": route,
        "reason": (
            "The phone evidence matches the frozen portal status."
            if route == "verified_match"
            else "The phone evidence differs from the frozen portal status."
        ),
        "portal_status": case.portal_status,
        "phone_status": phone_status,
        "official_status": case.portal_status,
        "official_status_mutated": False,
        "next_authority": "human_review",
    }


def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = PHONE_LIKE.sub("[phone-redacted]", value)
        value = EMAIL_LIKE.sub("[email-redacted]", value)
        return TOKEN_LIKE.sub("[credential-redacted]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def preview(case: PermitCase) -> dict[str, Any]:
    reason = call_reason(case)
    if reason is None:
        return no_call_result(case)
    arguments = call_arguments(case)
    arguments["recipients"][0]["phones"] = [case.public_dict()["agency_phone"]]
    return {
        "mode": "preview",
        "creates_phone_call": False,
        "call_reason": reason,
        "portal_snapshot": portal_snapshot(case),
        "snapshot_hash": snapshot_hash(case),
        "idempotency_key": idempotency_key(case),
        "call_arguments": arguments,
        "authority_boundary": "Phone evidence never mutates official permit status.",
    }


def simulated_result(case: PermitCase, scenario: str) -> dict[str, Any]:
    examples = {
        "verified-match": (case.portal_status, "OFFICE-7420"),
        "discrepancy": ("correction_required", "OFFICE-7421"),
        "unknown": ("unknown", "unknown"),
        "voicemail": ("unknown", "unknown"),
    }
    phone_status, reference = examples[scenario]
    structured = {
        "consented_after_ai_disclosure": "yes" if scenario != "voicemail" else "unknown",
        "right_permit_office": "yes" if scenario != "voicemail" else "unknown",
        "permit_reference_confirmed": "yes" if scenario != "voicemail" else "unknown",
        "phone_status": phone_status,
        "next_required_action": (
            "Submit the requested corrections before review can continue."
            if scenario == "discrepancy"
            else "Continue monitoring the official portal."
        ),
        "missing_items_summary": (
            "Correct the site plan setback labels."
            if scenario == "discrepancy"
            else "No missing items stated."
        ),
        "agency_reference": reference,
        "evidence_summary": "The office stated the current status and supplied a reference.",
    }
    provider = {
        "id": "simulation-call",
        "status": "completed",
        "task_completed": scenario != "voicemail",
        "completion_confidence": {"score": 0.95, "label": "high"},
        "structured_result": structured,
        "evidence": ["Synthetic no-call evidence for deterministic route testing."],
        "metadata": call_arguments(case)["metadata"],
        "recipients": [
            {
                "phone": case.agency_phone,
                "attempts": [
                    {
                        "transcript_turns": [
                            {
                                "speaker": "recipient",
                                "text": f"The office reference is {reference}.",
                            }
                        ]
                    }
                ],
            }
        ],
    }
    return {
        "mode": "simulate",
        "creates_phone_call": False,
        "scenario": scenario,
        "structured_result": structured,
        "decision": route_result(case, provider, expected_call_id="simulation-call"),
    }
