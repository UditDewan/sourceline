# Validation record

What was actually run against Sourceline, and what was not. Updated 2026-09-11.

Reproduce every claim on this page with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend -p 'test_*.py' -v
npm --prefix frontend run build
```

## What ran

| Check | Command | Result |
| --- | --- | --- |
| Backend test suite | `python -m unittest discover -s backend -p 'test_*.py'` | 6 tests, OK, 0.35s |
| TypeScript type check | `tsc --noEmit` (inside `npm run build`) | No errors |
| Frontend production build | `npm --prefix frontend run build` | Bundle emitted to `frontend/dist` |
| CI on push and pull request | `.github/workflows/checks.yml` | Same four steps on Python 3.14 / Node 24 |

Each test runs against a temporary SQLite file via `SOURCELINE_DB`, so no run touches the development database.

## What the tests cover

**`test_source_evidence_and_reconciliation`** — Every field of a complete packet reaches `verified`, and every piece of evidence is checked back against the document: the quote must equal the actual text at that one-based line. Conflicting, missing and invalid fields each produce the matching state, a `null` value and a finding code. A field appearing twice with different values keeps both evidence entries rather than silently picking one. A UTF-8 BOM at the start of a Windows export does not break label matching.

**`test_numeric_validation_and_consistency`** — `NaN`, `Infinity`, `-1`, `1e6`, `1.5`, `$1,00`, a value above the ceiling and `0` are all rejected for total insured value, and none of them reach the portfolio total. A zero loss count against a positive loss total raises `loss_inconsistency`.

**`test_ready_gate_atomic_reviews_and_persistence`** — The ready gate is enforced server-side: a packet with blockers returns 422 and its status, version and event count are unchanged afterward. A clean review returns 200, increments the version, and appends the reviewer and note to the history. Replaying the same request returns 409, so a stale browser cannot overwrite a newer review. Records, events and the export payload survive an application restart.

**`test_request_boundaries_and_sql_parameterization`** — Unknown fields, empty document lists, blank names and oversized text are rejected at the schema boundary. A cross-origin write returns 403; an unrecognized `Host` header returns 400. SQL metacharacters submitted as an insured name and as a reviewer note are stored and returned verbatim, with the table intact — parameterized queries, not escaping.

**`test_chunked_body_enforces_aggregate_limit`** — The 1 MB request limit is measured from the bytes actually received, not from a client-supplied `Content-Length`. A chunked body that lies about its length still gets a 413, and nothing reaches the application.

**`test_bedrock_selects_server_rendered_fields_or_saves_nothing`** — With a mocked client: an unconfigured model returns 503 and saves nothing. A valid selection produces a brief whose text is rendered by the server from its own field values. A model that returns prose, an object, an empty list or a non-string key returns 502 and saves nothing — model output selects which facts to show and can never author them.

## What was not tested

- **Live AWS Bedrock.** Every Bedrock test uses a mocked `boto3` client. No real model, region, credential chain or billing path has been exercised. Behavior against a live endpoint is unverified.
- **The browser.** There are no end-to-end or component tests. The frontend is covered only by `tsc --noEmit` and a successful build. The interface was exercised by hand during development, which is not a regression check.
- **Concurrency under load.** Review conflicts are tested sequentially against `BEGIN IMMEDIATE` and the version check. No parallel-writer or load test has been run.
- **Real documents.** The extractor reads labeled text only. There is no PDF, OCR or free-form parsing, and none was tested. All six samples are synthetic.
- **Security review.** Input validation, parameterized SQL, the origin and host checks and the body limit are tested as written. That is not a penetration test or an audit, and this application has no authentication.

## Limitations that are by design

The audit history is append-only through the application; it is not tamper-proof against anyone holding the database file. Reviewer identity is self-declared. "Source matched" means a value was found in the submitted text, not verified against the world. The review rules are illustrative, versioned as `demo-1`, and are not any carrier's risk appetite.

No performance claims are made about production insurance systems.
