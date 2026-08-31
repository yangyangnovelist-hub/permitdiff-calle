# Judge guide

## Ninety-second path

1. Choose **Fresh + clean**, then evaluate the policy: `no_call_needed` proves the zero-call path.
2. Choose **Conflicting record**, then **Show discrepancy**: the difference becomes obvious while
   the official record remains unchanged.
3. Inspect the stale-record preview for the exact CALL-E task, schema and snapshot hash.
4. Run the tests and inspect `tests/test_sdk_runtime.py` for the real official-SDK HTTP round trip.
5. Inspect a public live artifact only if it exists; no real-provider success is claimed otherwise.

## Four official criteria

- **Real-world impact:** reduces avoidable permit-office calls and makes exceptions actionable.
- **Quality of idea:** the product knows when not to call and refuses unofficial record authority.
- **Technical implementation:** official SDK runtime, strict schema, snapshot binding, corroboration,
  idempotency and fail-closed routing.
- **Product experience and demo:** fresh, matched and discrepant states are legible in one screen.
