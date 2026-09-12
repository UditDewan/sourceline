# Why this project exists

Commercial property and casualty insurers review broker submissions before anything is priced or bound. A submission packet is a set of documents describing a proposed risk: the insured, the location, what the building is used for, what it is worth, what limit is requested, and what has gone wrong there before.

Those packets disagree with themselves. The same field appears twice with two values. A required fact is missing. A number is malformed. Someone has to find that, reconcile it against the source, and decide whether the packet can move forward.

**Sourceline** is an independent prototype of that workflow on synthetic records. It demonstrates intake, evidence reconciliation and human review. It does not estimate premiums, determine coverage, or reproduce any carrier's underwriting guidelines.

## What the prototype actually claims

| Claim | Basis |
| --- | --- |
| Submission packets contain missing, conflicting and invalid facts | The core problem being modeled; the six synthetic samples cover each case |
| Every extracted value traces to a document and a one-based line | Implemented in `extract()`; asserted in `test_source_evidence_and_reconciliation` |
| A packet with unresolved facts cannot be marked ready | Server-side gate in `POST /api/submissions/{id}/review`, not a UI affordance |
| The review history is append-only through the application | Events table is insert-only; not tamper-proof against database owners |

"Source matched" means a value was located in the submitted text. It is not independent verification of the real world.

## Dependency decisions

| Dependency | Purpose | Why this one |
| --- | --- | --- |
| Python + React + TypeScript + SQL | API, processing, interface and persisted records | The stack the workflow needs: a typed boundary, a review surface, durable records |
| FastAPI + Pydantic + Uvicorn | HTTP API, typed boundary validation and server | Validation at the trust boundary comes from the schema, not hand-written checks |
| SQLite | Single-machine relational persistence with transactions | Runs with no setup. A shared deployment would need PostgreSQL or SQL Server |
| Vite + TypeScript compiler | Build the React application | Build speed; `tsc --noEmit` keeps the type check honest |
| unittest + HTTPX TestClient | Reproducible processing and API checks | Standard library test runner; no framework to learn |
| AWS SDK for Python (boto3), optional | Calls Bedrock Converse for a constrained reviewer brief | Opt-in only; the deterministic parser stays authoritative |

Exact versions tested are recorded in the lockfiles. No extra cloud providers or data platforms were added to lengthen the list. The working default needs no account and no API key. Bedrock is opt-in and cannot change extracted facts, review status or rules.

## How to present it

Lead with the business problem: inconsistent submission documents make reviewers spend their time finding and reconciling facts rather than judging risk.

Then show it. Open a submission with a conflicting value and follow the evidence to the exact source lines in two documents. Try to mark an incomplete packet ready and watch the server refuse, even with the interface bypassed. Review a clean submission, save a reviewer note, and export the review record.

Describe it accurately: an independent prototype on synthetic data, not a carrier integration and not a production insurance system. Use [the validation record](VALIDATION.md) to discuss what was actually tested and what was not.
