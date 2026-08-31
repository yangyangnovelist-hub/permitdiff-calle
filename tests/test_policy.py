import copy

import pytest

from permitdiff.models import age_hours, mask_phone, parse_request
from permitdiff.policy import (
    build_task,
    call_arguments,
    call_reason,
    idempotency_key,
    no_call_result,
    preview,
    redact,
    result_schema,
    route_result,
    simulated_result,
    snapshot_hash,
    valid_result,
)

RAW = {
    "case_id": "case-BL-2026-1842",
    "permit_number": "BL-2026-1842",
    "jurisdiction": "Example City",
    "agency_name": "Example City Permit Office",
    "agency_phone": "+15555550123",
    "authorized_agency_contact": True,
    "applicant_business_name": "Acme Construction",
    "portal_status": "in_review",
    "portal_updated_at_utc": "2026-08-25T08:00:00Z",
    "checked_at_utc": "2026-08-30T08:00:00Z",
    "portal_note": "Plan review is still in progress with no missing items shown.",
    "freshness_window_hours": 48,
    "conflict_flags": [],
    "region": "US",
    "locale": "en-US",
}


def fresh_raw():
    value = copy.deepcopy(RAW)
    value["portal_updated_at_utc"] = "2026-08-30T00:00:00Z"
    return value


def provider(case, scenario="discrepancy"):
    structured = simulated_result(case, scenario)["structured_result"]
    return {
        "id": "call-001",
        "status": "completed",
        "task_completed": scenario != "voicemail",
        "completion_confidence": {"score": 0.95, "label": "high"},
        "structured_result": structured,
        "evidence": ["Recipient-side office evidence captured."],
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
    }


def test_parse_snapshot_age_and_public_mask():
    case = parse_request(RAW)
    assert age_hours(case) == 120
    assert case.public_dict()["agency_phone"] == "+15******123"
    assert mask_phone(case.agency_phone) == "+15******123"
    assert snapshot_hash(case) == snapshot_hash(parse_request(copy.deepcopy(RAW)))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("case_id", "bad id!", "safe identifier"),
        ("agency_phone", "555", "E.164"),
        ("authorized_agency_contact", False, "must be true"),
        ("portal_status", "maybe", "unsupported"),
        ("region", "usa", "uppercase"),
        ("locale", "english", "look like"),
        ("agency_name", "api key secret", "credentials"),
        ("portal_note", "contact me@example.com", "contact data"),
    ],
)
def test_parse_rejects_unsafe_or_invalid_fields(field, value, message):
    raw = copy.deepcopy(RAW)
    raw[field] = value
    with pytest.raises(ValueError, match=message):
        parse_request(raw)


def test_parse_rejects_time_threshold_and_conflict_errors():
    raw = copy.deepcopy(RAW)
    raw["checked_at_utc"] = "2026-08-24T08:00:00Z"
    with pytest.raises(ValueError, match="cannot precede"):
        parse_request(raw)
    raw = copy.deepcopy(RAW)
    raw["freshness_window_hours"] = True
    with pytest.raises(ValueError, match="integer"):
        parse_request(raw)
    raw = copy.deepcopy(RAW)
    raw["conflict_flags"] = ["invented"]
    with pytest.raises(ValueError, match="unsupported"):
        parse_request(raw)
    raw = copy.deepcopy(RAW)
    raw["conflict_flags"] = ["timeline_conflict", "timeline_conflict"]
    with pytest.raises(ValueError, match="unique"):
        parse_request(raw)


def test_exception_first_policy_skips_fresh_and_calls_only_stale_or_conflicting():
    fresh = parse_request(fresh_raw())
    stale = parse_request(RAW)
    conflict_raw = fresh_raw()
    conflict_raw["conflict_flags"] = ["status_note_conflict"]
    assert call_reason(fresh) is None
    assert call_reason(stale) == "stale_portal_record"
    assert call_reason(parse_request(conflict_raw)) == "conflicting_portal_evidence"
    skipped = no_call_result(fresh)
    assert skipped["route"] == "no_call_needed"
    assert skipped["creates_phone_call"] is False
    assert skipped["official_status_mutated"] is False


def test_preview_distinguishes_zero_call_from_exception_call():
    skipped = preview(parse_request(fresh_raw()))
    assert skipped["route"] == "no_call_needed"
    stale = preview(parse_request(RAW))
    assert stale["mode"] == "preview"
    assert stale["creates_phone_call"] is False
    assert RAW["agency_phone"] not in str(stale)
    assert stale["call_reason"] == "stale_portal_record"


def test_task_and_arguments_make_calle_bounded_and_load_bearing():
    case = parse_request(RAW)
    task = build_task(case)
    assert "AI calling assistant" in task
    assert "correct permit office" in task
    assert "Do not request a status change" in task
    arguments = call_arguments(case)
    assert arguments["metadata"]["workflow_type"] == "permit_record_reconciliation"
    assert arguments["metadata"]["snapshot_hash"] == snapshot_hash(case)
    assert arguments["recipients"][0]["phones"] == [RAW["agency_phone"]]
    assert result_schema()["additionalProperties"] is False
    assert idempotency_key(case).startswith("permitdiff-")


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [("verified-match", "verified_match"), ("discrepancy", "discrepancy_detected")],
)
def test_route_accepts_corroborated_evidence_without_mutating_official_status(scenario, expected):
    case = parse_request(RAW)
    routed = route_result(case, provider(case, scenario), expected_call_id="call-001")
    assert routed["route"] == expected
    assert routed["official_status"] == "in_review"
    assert routed["official_status_mutated"] is False
    assert routed["next_authority"] == "human_review"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value.update(status="queued"), "terminal"),
        (lambda value: value.update(completion_confidence={"score": 0.1}), "terminal"),
        (lambda value: value.update(structured_result={}), "schema"),
        (lambda value: value.update(metadata={}), "approved portal"),
        (lambda value: value.update(id="wrong"), "approved portal"),
        (lambda value: value.update(evidence=[]), "approved portal"),
        (lambda value: value["recipients"][0].update(phone="+15555550999"), "approved portal"),
        (
            lambda value: value["structured_result"].update(
                consented_after_ai_disclosure="no"
            ),
            "consent",
        ),
        (
            lambda value: value["structured_result"].update(agency_reference="OTHER-999"),
            "corroborated",
        ),
    ],
)
def test_route_fails_closed_for_unreliable_or_unbound_evidence(mutation, reason):
    case = parse_request(RAW)
    value = provider(case)
    mutation(value)
    routed = route_result(case, value, expected_call_id="call-001")
    assert routed["route"] == "outcome_unknown"
    assert routed["official_status_mutated"] is False
    assert reason.casefold() in routed["reason"].casefold()


@pytest.mark.parametrize("scenario", ["unknown", "voicemail"])
def test_unknown_routes_never_become_official_status(scenario):
    result = simulated_result(parse_request(RAW), scenario)
    assert result["decision"]["route"] == "outcome_unknown"
    assert result["decision"]["official_status_mutated"] is False


def test_schema_and_recursive_redaction():
    case = parse_request(RAW)
    value = provider(case)["structured_result"]
    assert valid_result(value)
    assert not valid_result({**value, "extra": "no"})
    assert not valid_result({**value, "phone_status": "wishful"})
    assert not valid_result({**value, "agency_reference": ""})
    redacted = redact({"items": ["+15555550123", "me@example.com", "token: abc"]})
    assert "+15555550123" not in str(redacted)
    assert "me@example.com" not in str(redacted)
    assert "abc" not in str(redacted)
