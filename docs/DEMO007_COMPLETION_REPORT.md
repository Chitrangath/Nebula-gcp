# DEMO-007 Completion Report

## Outcome

Nebula now has an authenticated `/network` page that represents the connected AI-user browser and every registered GPU node in one live, credential-free view.

- `GET /v1/network` returns the authenticated viewer, configured chain and Verifier authority, provider wallets, effective heartbeat state, model capabilities, current leases, and each node's last completed job.
- Effective `online` state expires when the last heartbeat exceeds the configured scheduler TTL, so the page does not repeat a stale database label as live availability.
- Provider and Verifier roles are displayed from backend identities; API keys, hashes, worker signer identities, proof envelopes, and private inputs are excluded.
- The responsive page refreshes automatically every 10 seconds and on demand, with one contextual live-region update rather than competing badge announcements.
- The evidence-boundary panel distinguishes backend-observed runtime state from Arbitrum Sepolia settlement authority.

Production acceptance remains in DEMO-008: deploy the backend/frontend revisions, connect Device A, start both independent provider Workers, and visibly exercise heartbeat, lease, and completed-job changes.

## Interfaces and trust boundaries

- `GET /v1/network` is authenticated but intentionally cross-provider: participants may observe public demo identities and operational state without receiving provider credentials or private job artifacts.
- The connected browser represents the authenticated wallet. Registered GPU-node cards represent provider-operated machines, not wallets or Workers themselves.
- Provider and Verifier addresses link to Arbiscan because they are public chain identities. Lease and job history remain explicitly labeled backend-observed.
- The module batches node, active-lease, and completed-job reads behind one typed response interface; browser code consumes generated OpenAPI types.

## Verification

- Backend: `367 passed, 71 skipped` across the complete suite, including local Anvil integration coverage.
- Frontend: `75 passed` across 15 test files.
- ESLint, Ruff, TypeScript, generated OpenAPI synchronization, contract-artifact checks, and the production Vite build pass.
- Targeted mypy reports no error in the new network router after its model-boundary casts. Existing transitive settings and untyped third-party dependency errors remain in the repository baseline.

## Phase 4 and Phase 6 Skill Usage

### Discovered Skills

- solidity-foundry-security, tdd, domain-modeling, code-review, diagnosing-bugs, research, codebase-design, grill-with-docs, improve-codebase-architecture, handoff, ask-matt, setup-matt-pocock-skills, teach, wizard, banner-design, brand, design, design-system, slides, ui-styling, ui-ux-pro-max.

### Applied Skills

1. **tdd**: Confirmed the authenticated `GET /v1/network` and rendered `/network` page as the public seams, observed 404/import failures, and completed backend then browser vertical slices.
2. **domain-modeling**: Distinguished Demo device, GPU node, Worker, wallet, AI user, GPU provider, and Verifier; recorded Demo device in `CONTEXT.md` to prevent the UI projection from implying a blockchain peer network.
3. **codebase-design**: Kept aggregation, TTL-derived availability, role mapping, and credential exclusion behind one typed network interface instead of spreading database knowledge into the browser.
4. **ui-ux-pro-max**: Used the verified minimal/Swiss dashboard direction, contextual live-status guidance, stable list keys, text-plus-color status, and no blanket React memoization. The first React polling query returned no result; the required narrower retry returned applicable list guidance.
5. **ui-styling**: Applied semantic regions, visible focus rings, 44px controls/links, long-token wrapping, readable evidence grouping, and mobile-first grids using the existing Tailwind system.
6. **code-review**: The mandatory independent Standards and Spec reviews are run after the implementation commit and recorded below.

### Not Applied

- **solidity-foundry-security**: No contract or ABI changed.
- **diagnosing-bugs**: The only full-suite failure was a brittle new test ordering assumption, corrected without a product defect investigation.
- **research**: Repository requirements and existing runtime semantics were sufficient; no external product fact was required.
- **grill-with-docs**: The execution plan already fixed the acceptance criteria.
- **improve-codebase-architecture**: No broad refactor was needed beyond the focused projection module.
- **handoff**, **ask-matt**, **setup-matt-pocock-skills**, **teach**: No session transition, skill routing, installation, or teaching task was requested.
- **wizard**: No human-only credential or third-party dashboard action was introduced.
- **banner-design**, **brand**, **design**, **design-system**, **slides**: No campaign asset, identity program, presentation, or product-wide token change was required.

## Review result

The independent Standards and Spec reviews found no blocking or high-severity issue. Their four medium-severity findings were resolved before handoff:

1. Verifier placement now uses the explicit `DEMO_VERIFIER_NODE_ID` configuration instead of assuming the Verifier key belongs to a provider or Worker identity.
2. Heartbeat freshness compares timestamps at full precision against the scheduler TTL; a regression covers the sub-second expiry boundary.
3. Latest completed work is selected per node with a ranked database query instead of loading every historical completed job on each poll.
4. Automatic polling is scheduled after both successful and failed requests, and a browser test proves recovery from a transient failure.

The low-severity accessibility observation was also resolved: the changing announcement contains only contextual node/lease totals, while the observation timestamp remains visible but outside the live region.

**Final review disposition:** PASS. No unresolved Standards or Spec finding remains in the DEMO-007 implementation.
