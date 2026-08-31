# Threat model

| Failure | Control | Safe result |
|---|---|---|
| Fresh digital record creates needless phone work | Freshness and conflict policy runs before SDK construction | `no_call_needed` |
| Phone answer is applied as permit truth | Route always returns `official_status_mutated=false` | Human review only |
| Wrong office or permit | Explicit office consent and permit-reference confirmation | `outcome_unknown` |
| Result belongs to another snapshot | Bind call ID, case, permit, destination and snapshot hash | `outcome_unknown` |
| Model invents an office reference | Reference must occur in recipient-side transcript evidence | `outcome_unknown` |
| Voicemail or uncertainty is presented as status | Terminal, confidence, schema and known-status gates | `outcome_unknown` |
| Duplicate or uncertain dispatch | SQLite reservation precedes provider dispatch | Retry blocked for reconciliation |
| Sensitive applicant data enters the call | Input validation and task prohibit PII, credentials and access codes | Request rejected |

PermitDiff does not file forms, request approval, schedule inspections, pay fees or change municipal
records. It reconciles one frozen non-sensitive snapshot for human review.
