# Consented live discrepancy validation

Use only a number you own or a consenting adult has explicitly authorized. The recipient should
know CALL-E will identify itself as an AI assistant and should answer the synthetic permit scenario
honestly. Do not coach a false discrepancy.

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
