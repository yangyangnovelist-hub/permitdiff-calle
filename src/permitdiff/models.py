"""Validated, non-personal permit portal snapshot for one bounded reconciliation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,79}$")
LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
REGION = re.compile(r"^[A-Z]{2}$")
PHONE_LIKE = re.compile(r"(?<!\w)\+?[1-9]\d{7,14}(?!\w)")
EMAIL_LIKE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRET_LIKE = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|password|private[_ -]?key|"
    r"client[_ -]?secret|credential|bearer)\b"
)
PORTAL_STATUSES = {"received", "in_review", "correction_required", "approved", "denied"}
CONFLICT_FLAGS = {"status_note_conflict", "timeline_conflict", "document_request_conflict"}


@dataclass(frozen=True)
class PermitCase:
    case_id: str
    permit_number: str
    jurisdiction: str
    agency_name: str
    agency_phone: str
    authorized_agency_contact: bool
    applicant_business_name: str
    portal_status: str
    portal_updated_at_utc: str
    checked_at_utc: str
    portal_note: str
    freshness_window_hours: int
    conflict_flags: tuple[str, ...]
    region: str
    locale: str

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["agency_phone"] = mask_phone(self.agency_phone)
        return value


def clean_text(value: Any, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = " ".join(value.split())
    if not minimum <= len(cleaned) <= maximum:
        raise ValueError(f"{field} must contain {minimum}-{maximum} characters")
    return cleaned


def clean_spoken_text(value: Any, field: str, minimum: int, maximum: int) -> str:
    cleaned = clean_text(value, field, minimum, maximum)
    if SECRET_LIKE.search(cleaned) or PHONE_LIKE.search(cleaned) or EMAIL_LIKE.search(cleaned):
        raise ValueError(f"{field} appears to contain credentials or personal contact data")
    return cleaned


def parse_utc(value: Any, field: str) -> datetime:
    text = clean_text(value, field, 20, 35)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{field} must use UTC")
    return parsed.astimezone(UTC)


def format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse_request(raw: Any) -> PermitCase:
    if not isinstance(raw, dict):
        raise ValueError("request must be a JSON object")

    case_id = clean_text(raw.get("case_id"), "case_id", 3, 80)
    permit_number = clean_text(raw.get("permit_number"), "permit_number", 3, 80)
    if not SAFE_ID.fullmatch(case_id) or not SAFE_ID.fullmatch(permit_number):
        raise ValueError("case_id and permit_number may contain only safe identifier characters")

    phone = clean_text(raw.get("agency_phone"), "agency_phone", 1, 32)
    if not E164.fullmatch(phone):
        raise ValueError("agency_phone must use E.164 format")
    if raw.get("authorized_agency_contact") is not True:
        raise ValueError("authorized_agency_contact must be true")

    status = raw.get("portal_status")
    if status not in PORTAL_STATUSES:
        raise ValueError("portal_status is unsupported")
    updated = parse_utc(raw.get("portal_updated_at_utc"), "portal_updated_at_utc")
    checked = parse_utc(raw.get("checked_at_utc"), "checked_at_utc")
    if checked < updated:
        raise ValueError("checked_at_utc cannot precede portal_updated_at_utc")

    freshness = raw.get("freshness_window_hours")
    if isinstance(freshness, bool) or not isinstance(freshness, int) or not 1 <= freshness <= 336:
        raise ValueError("freshness_window_hours must be an integer from 1 to 336")

    conflicts = raw.get("conflict_flags", [])
    if not isinstance(conflicts, list) or any(item not in CONFLICT_FLAGS for item in conflicts):
        raise ValueError("conflict_flags contains an unsupported flag")
    if len(set(conflicts)) != len(conflicts):
        raise ValueError("conflict_flags must be unique")

    region = clean_text(raw.get("region"), "region", 1, 16)
    if not REGION.fullmatch(region):
        raise ValueError("region must be a two-letter uppercase country code")
    locale = clean_text(raw.get("locale", "en-US"), "locale", 2, 16)
    if not LOCALE.fullmatch(locale):
        raise ValueError("locale must look like en-US")

    return PermitCase(
        case_id=case_id,
        permit_number=permit_number,
        jurisdiction=clean_spoken_text(raw.get("jurisdiction"), "jurisdiction", 2, 100),
        agency_name=clean_spoken_text(raw.get("agency_name"), "agency_name", 2, 100),
        agency_phone=phone,
        authorized_agency_contact=True,
        applicant_business_name=clean_spoken_text(
            raw.get("applicant_business_name"), "applicant_business_name", 2, 100
        ),
        portal_status=status,
        portal_updated_at_utc=format_utc(updated),
        checked_at_utc=format_utc(checked),
        portal_note=clean_spoken_text(raw.get("portal_note"), "portal_note", 2, 300),
        freshness_window_hours=freshness,
        conflict_flags=tuple(conflicts),
        region=region,
        locale=locale,
    )


def age_hours(case: PermitCase) -> float:
    updated = datetime.fromisoformat(case.portal_updated_at_utc.replace("Z", "+00:00"))
    checked = datetime.fromisoformat(case.checked_at_utc.replace("Z", "+00:00"))
    return (checked - updated).total_seconds() / 3600


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}{'*' * max(4, len(phone) - 6)}{phone[-3:]}"
