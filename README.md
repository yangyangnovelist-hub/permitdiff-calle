# PermitDiff

[![CI](https://github.com/yangyangnovelist-hub/permitdiff-calle/actions/workflows/ci.yml/badge.svg)](https://github.com/yangyangnovelist-hub/permitdiff-calle/actions/workflows/ci.yml)

**An exception-first permit agent: fresh records trigger no call; stale or conflicting records get
one evidence-bound CALL-E check that never becomes permit truth.**

[Open the judge console](https://permitdiff.vercel.app/) ·
[Inspect the published reconciliation desk](https://yangyangnovelist-hub.github.io/permitdiff-calle/) ·
[Review the merged CALL-E contribution](https://github.com/CALLE-AI/awesome-phone-call-agents/pull/199) ·
[Inspect the stale-record preview](artifacts/example-preview.json) ·
[Inspect the deterministic discrepancy](artifacts/example-simulation.json) ·
[Run the verification suite](TESTING.md)

## What a judge can verify

1. Open the judge console, choose **Fresh + clean**, then **Evaluate call policy**. The route
   becomes `no_call_needed`; no CALL-E request is produced.
2. Choose **Conflicting record**, then **Show discrepancy**. The phone status changes to
   `correction_required`, a human-review stamp appears, and the official record remains unchanged.
3. Inspect `artifacts/example-preview.json` for the exact CALL-E task, frozen portal snapshot hash,
   masked destination, strict schema and idempotency key.
4. Run `uv run pytest --cov=src/permitdiff`. The suite imports `calle-ai==0.2.0`, observes a real SDK
   `POST /v1/calls` and poll on a loopback server, and verifies the bound discrepancy route. Tests
   never contact an external phone number.

## Decisive proof sequence

```text
freeze portal snapshot
  → fresh + consistent? return no_call_needed
  → stale or conflicting? authorize exactly one office destination
  → CALL-E discloses AI and asks bounded reconciliation questions
  → bind call, case, permit, destination, snapshot hash and recipient evidence
  → verified_match / discrepancy_detected / outcome_unknown
  → human reviews; official portal status never changes
```

The distinctive mechanism is **exception-first calling**. PermitDiff reduces unnecessary phone work
instead of scaling a dialer, and it treats a phone answer as reviewable evidence rather than an
unofficial record update.

## Why CALL-E is load-bearing

CALL-E performs the bounded office conversation and returns the current phone status, next required
action, missing items, office reference and evidence summary. PermitDiff decides whether a call is
warranted, creates the strict task and schema, binds evidence to the frozen portal snapshot, and
routes differences without granting the phone result authority over the record.

## Run locally

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev

# Stale-record preview; creates no call
uv run permitdiff --request examples/example.json

# Deterministic no-call proof routes
uv run permitdiff --request examples/example.json --simulate verified-match
uv run permitdiff --request examples/example.json --simulate discrepancy
uv run permitdiff --request examples/example.json --simulate unknown
uv run permitdiff --request examples/example.json --simulate voicemail

# Browser operator surface; live execution remains disabled
uv run permitdiff-web
```

Then open `http://127.0.0.1:8768/`.

## Live execution boundary

Only call a number you own or a consenting adult has explicitly authorized for the synthetic test.
Live mode requires `CALLE_API_KEY`, `CALLE_LIVE_CALLS_ENABLED=true`, an exact E.164 allowlist,
recipient authorization, explicit confirmation that phone evidence cannot write a record, and a
fresh durable idempotency reservation.

The one-shot protocol is in [`LIVE-VALIDATION.md`](LIVE-VALIDATION.md). Failed, ambiguous or
non-discrepant outcomes stay local and are not blindly retried.

## Trust model and limitations

- Fresh and consistent records return `no_call_needed` before SDK construction.
- The task asks only about one non-sensitive permit reference and prohibits personal data,
  credentials, payment data, access codes, filings, scheduling and status-change requests.
- Accepted results bind the call ID, case, permit, exact destination and frozen portal snapshot,
  and corroborate the office reference against recipient-side evidence.
- Wrong office, no consent, unknown status, malformed result, low confidence, wrong metadata,
  voicemail or missing corroboration returns `outcome_unknown`.
- `official_status_mutated` is always false; a discrepancy can only route to human review.
- PermitDiff is not a permit authority, filing service, inspection scheduler, legal adviser, or
  source of official status.

See [`THREAT_MODEL.md`](THREAT_MODEL.md).

## Verification status

- 53 automated tests pass with 90.95% coverage.
- Ruff passes with no findings.
- CI validates HTML semantics and audits the locked runtime dependency graph for known vulnerabilities.
- Desktop and mobile browser paths have been exercised with headless Chromium.
- The official CALL-E SDK is invoked at runtime in the HTTP integration test.
- The implementation is merged into CALL-E's official phone-agent repository through
  [PR #199](https://github.com/CALLE-AI/awesome-phone-call-agents/pull/199).
- A public real-provider discrepancy is not claimed until the consented live protocol succeeds.

## What was built during the event

The permit snapshot model, freshness and conflict policy, CALL-E task and strict schema, runtime
adapter, durable reservation, evidence-binding reconciliation logic, CLI, operator console,
published interactive desk, consented live runner and verification suite were built during the
event.

PermitDiff reuses the official CALL-E SDK and reliability patterns from the author's MIT-licensed
IncidentBridge project. Its exception policy, domain schema, reconciliation routes, authority
boundary, UI and evidence contract are independent. See [`THIRD_PARTY.md`](THIRD_PARTY.md).

MIT licensed.
