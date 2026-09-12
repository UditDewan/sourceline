# Resume bullets — Sourceline

Google's XYZ method: *Accomplished **[X]**, as measured by **[Y]**, by doing **[Z]**.*

- **Built an evidence-linked submission review workbench for commercial-property insurance intake** (Python/FastAPI, React/TypeScript, SQLite), **as measured by** all 10 extracted fields resolving to a named document and one-based line number, zero unverified or conflicting values reaching portfolio totals, and 6 automated tests passing in CI, **by** writing a deterministic labeled-text extractor that keeps every candidate value with its source evidence and marks a field `conflict`, `invalid` or `missing` rather than guessing a winner.
  *Backing: `backend/main.py` `extract()`; `test_source_evidence_and_reconciliation` asserts each quote equals the document text at its cited line.*

- **Hardened the review API against malformed, cross-origin and stale writes**, **as measured by** 8 malformed numeric formats (`NaN`, `Infinity`, `-1`, `1e6`, `1.5`, `$1,00`, out-of-range, `0`) rejected at the schema boundary, oversized bodies refused before reaching application code, and concurrent reviews returning HTTP 409 instead of silently overwriting, **by** validating with Pydantic at the trust boundary, enforcing the 1 MB request limit on bytes actually received rather than a client-supplied `Content-Length`, and gating every status change on a record version inside a transaction.
  *Backing: `backend/main.py` `RequestBoundary` and `review()`; `test_numeric_validation_and_consistency`, `test_request_boundaries_and_sql_parameterization`, `test_chunked_body_enforces_aggregate_limit`.*
