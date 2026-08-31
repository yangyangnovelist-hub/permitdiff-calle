# Testing

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest --cov=src/permitdiff --cov-report=term-missing --cov-fail-under=90
```

The SDK integration test starts a loopback HTTP server, imports `calle-ai==0.2.0`, observes the
authenticated `POST /v1/calls`, idempotency key, strict result schema and snapshot metadata, then
observes `GET /v1/calls/{id}`. No test contacts an external phone number.

Critical regressions cover fresh-record call suppression, conflict escalation, missing consent,
unsupported destinations, duplicate dispatch, low confidence, malformed schema, wrong call ID,
wrong snapshot hash, wrong recipient, missing evidence, uncorroborated office references, unknown
status, voicemail, and any attempt to turn phone evidence into official status.
