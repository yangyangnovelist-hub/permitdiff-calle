# Consented live discrepancy validation

Use only a number you own or a consenting adult has explicitly authorized. This is a fixed
role-play fixture, not a call to a real permit office. The recipient should know CALL-E will
identify itself as an AI assistant and should answer only from the fixture below. Never call a
government office, random business or uninvolved third party for this validation.

## Fixed recipient fixture

The consenting participant role-plays the Example City Permit Office for this synthetic test. The
following facts are frozen before dispatch:

- this is the correct office for the synthetic role-play, and the participant consents after the
  AI disclosure;
- permit `BL-2026-1842` is confirmed;
- current phone-reported status: `correction_required`;
- next action: submit the requested corrections before review can continue;
- missing item: correct the site-plan setback labels; and
- office reference: `OFFICE-7421`.

The participant may answer naturally as the agent asks questions and does not need to read a
monologue. These facts are a deterministic test fixture, not a claim about a real permit.

```bash
export CALLE_API_KEY="<CALL_E_API_KEY>"
export CALLE_LIVE_CALLS_ENABLED="true"

uv run permitdiff-consented-live-demo \
  --phone +<AUTHORIZED_E164_NUMBER> \
  --confirm-consent "I HAVE EXPLICIT CONSENT" \
  --confirm-no-record-write "PHONE EVIDENCE WILL NOT ALTER THE RECORD"
```

At most one call is reserved. A successful discrepancy creates
`artifacts/consented-live-discrepancy.json` without publishing the number, identity, transcript or
recording. Any other outcome remains in `data/consented-live-last-result.json`; inspect it and do not
blindly retry.
