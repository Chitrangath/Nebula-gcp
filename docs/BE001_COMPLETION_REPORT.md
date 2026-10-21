# BE-001 Completion Report

## Outcome

The authenticated `POST /v1/jobs` seam now accepts a multipart file upload and
derives the private object key, input SHA-256, server UUID, chain job ID, price,
and job fingerprint on the backend. The public handler no longer accepts a
client-selected storage key, input hash, fingerprint, or price.

The internal `create_job` interface remains available to lifecycle and protocol
tests; this change intentionally affects only the browser-facing creation seam.

## Security and failure behavior

- Reads uploads in bounded 64 KiB chunks and stops once the approved model's
  byte limit is exceeded.
- Restricts filenames to one safe basename and constructs the storage key as
  `inputs/<server-job-uuid>/input.<validated-extension>`.
- Cross-checks the approved extension, exact MIME type, file magic, structural
  completeness, and bounded image dimensions for PNG/JPEG inputs.
- Requires a valid approved model artifact SHA-256 before fingerprinting.
- Uses immutable object creation. Local file storage writes and fsyncs a
  same-directory temporary file, then atomically links it into place and always
  removes the temporary file.
- Explicitly commits while cleanup remains possible; storage failures remove
  the pending row, and persistence failures roll back then remove abandoned
  bytes. Concurrent identical idempotent inserts resolve to the winning row.
- Supports bounded `Idempotency-Key` retries, returning the original job only
  for the same user, model, and exact bytes; reuse with different bytes is 409.
- Performs all upload validation and storage I/O without acquiring row locks.

## Verification

- New upload behavior suite: 11 passing tests, covering authoritative hashing,
  key construction, traversal, unsupported extension, MIME mismatch, magic
  mismatch, empty/truncated/over-limit input, pre/post-storage cleanup,
  idempotent duplicates, and conflicting duplicate bytes.
- Upload plus jobs-router slice: 17 passing tests.
- Full backend suite: 263 passed, 69 environment-gated tests skipped, one
  pre-existing pytest-asyncio deprecation warning.
- Ruff check and format: passed.
- New isolated validation module mypy: passed.
- Project-wide mypy remains a pre-existing baseline failure (364 errors in
  legacy untyped SQLAlchemy/router code); it was not widened into this ticket.

Public object-storage validation remains blocked on NET-003 and owner-provided
infrastructure. No public service, wallet, secret, or hosted resource was used.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `tdd`: exercised the authenticated upload seam through red-green vertical
   slices before implementation.
2. `codebase-design`: kept validation/canonicalization behind one small module
   interface and preserved the existing internal lifecycle seam.
3. `code-review`: two-axis standards/spec review is required before commit.

### Not applied

- `domain-modeling`: consumed `CONTEXT.md`; no domain term changed.
- `diagnosing-bugs`: no hard integration defect required its diagnosis loop.
- `solidity-foundry-security`: no contract was changed.
- `research`, `wizard`: no new external fact or owner-only action was needed.
- Remaining routing, teaching, refactoring, and handoff skills were outside this
  bounded implementation ticket.
