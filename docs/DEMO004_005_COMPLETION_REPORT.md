# DEMO-004 and DEMO-005 Completion Report

## Outcome

The production user job experience and provider dashboard are implemented against authoritative backend state.

- An AI user can discover the approved ResNet50 and BERT models, upload a bounded image or enter bounded UTF-8 text, review funding, complete escrow, and open the new job directly in the browser.
- The job page exposes escrow, queue, assignment, execution, proof, settlement, failure, and refund states. A successful terminal job renders the canonical model result and offers an authenticated download. Failed, refunded, or reconciliation-incident jobs never expose a result action.
- A GPU provider can see the authenticated wallet, owned GPU nodes, worker signer, heartbeat, model capabilities, current lease, recent completed work, earnings, and settlement links. Dashboard reads never return or render node credentials.
- Provider state refreshes every 15 seconds and offers an explicit retry after a failed read.

Production rollout is intentionally separate from implementation completion. The current Cloud Run revision and Vercel deployment must be updated before the new screens are visible publicly. The three physical-device journey remains the acceptance gate in DEMO-008.

## Interfaces and trust boundaries

- `GET /v1/models` remains the source of approved model metadata.
- `GET /v1/jobs/{job_id}` remains the source of job lifecycle, proof, settlement, and assignment state.
- `GET /v1/jobs/{job_id}/result` remains owner-scoped and integrity checked by the backend. The browser accepts only the two canonical result shapes and discards unknown fields.
- `GET /v1/nodes` remains provider-scoped and now includes public operational state: supported models, the current lease, and up to five recently completed jobs.
- `GET /v1/earnings` remains provider-scoped and supplies credit and settlement evidence.

## Verification

- Frontend: 64 component/module tests pass.
- Frontend: production TypeScript/Vite build passes.
- Frontend: ESLint passes with zero warnings.
- Backend: 361 tests pass and 71 environment/optional tests skip.
- Focused provider/job backend acceptance: 35 tests pass.
- OpenAPI document, manifest, and generated browser types are synchronized.
- Ruff passes for the modified backend source and tests.
- The configured mypy run was executed. It still reports the repository's existing SQLAlchemy 1.x-style `Column` typing and missing third-party stub baseline, including unchanged lines in the nodes router; runtime tests and generated contracts are clean.

## Phase 4 Skill Usage

### Discovered Skills

- solidity-foundry-security, tdd, domain-modeling, code-review, diagnosing-bugs, research, codebase-design, grill-with-docs, improve-codebase-architecture, handoff, ask-matt, setup-matt-pocock-skills, teach, wizard, banner-design, brand, design, design-system, slides, ui-styling, ui-ux-pro-max.

### Applied Skills

1. **tdd**: Added browser-page and provider-scoped HTTP acceptance tests first, observed the failures, and implemented one vertical behavior slice at a time.
2. **domain-modeling**: Kept the UI and response vocabulary aligned with `CONTEXT.md`: AI user, GPU provider, GPU node, Worker, Lease, PoAE proof, and Settlement.
3. **codebase-design**: Kept external seams small: typed job/node adapters hide parsing, aggregation, polling, and result validation from pages.
4. **ui-ux-pro-max**: Applied a compact flat dashboard direction, progressive funding disclosure, explicit recovery, text-plus-color states, visible focus, long-token wrapping, and responsive grids.
5. **ui-styling**: Reused the existing React/Tailwind system, semantic HTML, labelled controls, 44px minimum controls, accessible status regions, and mobile-first layouts without adding a component dependency.
6. **code-review**: Used the required standards and specification axes after implementation; findings and resolutions are recorded below.

### Not Applied

- **solidity-foundry-security**: No smart-contract change was made.
- **diagnosing-bugs**: No unresolved defect required the dedicated diagnosis loop; normal red/green failures were resolved within TDD.
- **research**: No external API or design fact required repository research.
- **grill-with-docs**: The execution plan already fixed the requirements and sequence.
- **improve-codebase-architecture**: No broad refactor was needed for these vertical slices.
- **handoff**: No session transition was requested.
- **ask-matt**, **setup-matt-pocock-skills**, **teach**: Skill routing, installation, and teaching were not part of the ticket.
- **wizard**: These tickets contain no human-only dashboard or credential step.
- **banner-design**, **brand**, **design**, **design-system**, **slides**: No campaign asset, identity redesign, presentation, or new product-wide design system was required.

## Review result

This section is completed after the two-axis review. Any blocking finding must be resolved before this report is committed.
