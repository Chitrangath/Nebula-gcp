# Nebula-gcp Frontend Enhancement Skill

## Product direction

Nebula should combine three reference experiences without copying their implementation:

- **io.net influence:** a visible GPU marketplace, provider capacity, node health, pricing, utilization, job queue, and live infrastructure signals.
- **Linear influence:** a fast, calm, keyboard-friendly product interface with a strong information hierarchy, command-style navigation, compact tables, clear status labels, and focused workflows.
- **Privy influence:** simple wallet onboarding, clear account and network state, understandable signing prompts, transaction progress, explorer links, and recovery from rejected transactions.

These are visual and interaction references. They do not authorize importing their APIs, authentication model, wallet architecture, branding, or proprietary assets.

Use this skill to improve the Nebula AI Cloud frontend safely and incrementally. The repository is a React 18 + TypeScript + Vite application under `frontend/`. It uses Tailwind CSS, React Router, `viem`, generated OpenAPI types, generated contract artifacts, Vitest, Testing Library, and Playwright.

## Non-negotiable safety rules

1. Inspect the repository before editing. Read the root `AGENTS.md`, `CONTEXT.md`, `frontend/package.json`, relevant routes/components, wallet code, API client, contract artifacts, and existing tests.
2. Preserve the current application boundary. Do not replace the router, wallet provider, `viem` clients, generated API files, generated contract files, backend endpoints, or environment variable names unless explicitly required.
3. Never assume Privy, embedded wallets, ERC-4337, MPC, SSE, WebSockets, Framer Motion, Radix, TanStack Query, or D3 are installed. Add a dependency only when the existing code and requested feature justify it.
4. Do not put secrets, private keys, RPC credentials, or signing material in frontend code.
5. Keep blockchain state authoritative. Optimistic UI may show pending, but must not show confirmed until the existing `viem` receipt or contract-read flow confirms it. Roll back after rejection, revert, timeout, or receipt failure.
6. Keep existing routes and primary flows working: wallet connection, AI-user job submission, GPU-provider/node views, job status, verification verdict, and settlement display.
7. Make small, reviewable changes. Prefer adding components, hooks, styles, and tests over rewriting working files. Search all usages before modifying a shared component.
8. Use `CONTEXT.md` terminology: AI user, job, GPU provider, GPU node, worker, lease, proof envelope, PoAE proof, verifier, verdict, and settlement.

## Required workflow

### 1. Baseline

- Identify the active branch and working tree state.
- Read repository instructions and frontend package scripts.
- Map routes, pages, shared UI, wallet flow, API calls, contract calls, state ownership, and tests.
- Record files to change and invariants to preserve.
- Run the smallest relevant existing check before editing when supported.

### 2. Design

Choose the smallest change that meets the request. Keep presentation, server/API state, and blockchain state separate:

- Presentation: dialogs, filters, tabs, focus, and animations.
- API state: jobs, nodes, leases, proof envelopes, verdicts, and settlement data.
- Chain state: account, transaction hash, receipt, contract reads, and settlement confirmation.

Use the existing architecture first. Introduce a new state library or transport only after confirming the current code cannot support the requirement.

### 3. Implementation

- Reuse existing TypeScript types and generated artifacts.
- Add explicit loading, empty, error, pending, confirmed, and stale states.
- Preserve accessibility: keyboard operation, visible focus, semantic controls, labels, dialog focus containment, and reduced-motion support.
- Use existing Tailwind tokens and responsive patterns.
- Avoid global shortcuts unless documented, scoped, and disabled in inputs, textareas, selects, and editable elements.
- Avoid `will-change` and GPU hints unless profiling shows they are needed.
- For live updates, use the transport already present. Validate payloads, handle reconnects, clean up subscriptions, and prevent duplicate updates. Never invent a stream endpoint.
- For long lists, paginate or limit first. Add virtualization only after measuring a real problem.

### Safe transaction pattern

Use the existing `viem` clients and contract interfaces. A transaction UI follows:

`idle → preparing → wallet confirmation → submitted(hash) → confirmed(receipt) | failed(error)`

Do not call `signUserOperation`, `sendUserOperation`, or an embedded-wallet API unless that integration already exists. Show an explorer link only when chain and transaction hash are known.

## Nebula UI priorities

Prioritize improvements useful for a faculty demonstration and real user flow:

1. Dashboard with wallet/network, available GPU nodes, active jobs, and terminal settlement status.
2. Guided job submission showing approved model, model artifact/version, exact input, fixed price, and transaction status.
3. Job timeline: submitted, leased, executing, proof envelope received, verifier verdict, and settlement.
4. Provider views for node registration, availability, lease assignment, execution, and earnings.
5. Human-readable proof and verdict details without claiming PoAE proves model correctness.
6. Reliable responsive behavior and useful loading/error states.

## Three-layer experience model

Organize the interface around three product layers:

### Infrastructure layer — io.net-inspired

- Show GPU nodes as real capacity with status, model compatibility, availability, region, utilization, and recent health.
- Show job queue and lease information using data returned by Nebula’s backend.
- Use live updates only when the repository already exposes a supported transport. Clearly label stale data and connection failures.
- Do not fabricate GPU metrics, provider earnings, node availability, or pricing for production screens. Demo-only fixtures must be visibly marked.

### Product layer — Linear-inspired

- Use a consistent application shell with sidebar navigation, breadcrumbs, page titles, compact cards, tables, filters, and a command menu only where it improves navigation.
- Keep one primary action per screen and make the next state obvious.
- Use restrained motion, predictable spacing, keyboard navigation, visible focus, and reduced-motion support.
- Model workflows as explicit states: draft, submitted, queued, leased, executing, verifying, settled, refunded, failed, or expired.

### Wallet layer — Privy-inspired

- Make wallet connection understandable to first-time users: connect, account identity, network, balance or payment requirement, and disconnect/switch actions.
- Explain what the user is signing before opening the wallet.
- Show transaction progress as preparing, awaiting wallet, submitted, confirming, confirmed, or failed.
- Keep wallet and contract behavior on the existing `viem` integration unless the repository explicitly adopts another provider.
- Never imply that a wallet connection or transaction proves AI inference correctness; that remains tied to the verifier verdict.

## Recommended information architecture

Use these sections when they fit the existing route structure:

- **Overview:** active jobs, available capacity, recent verdicts, settlement summary, and network status.
- **Jobs:** searchable job table with status, model/version, price, assigned node, timestamps, proof/verdict, and settlement.
- **GPU marketplace:** provider nodes, capabilities, availability, utilization, and lease details.
- **Submit job:** approved model selection, exact input, price summary, wallet confirmation, and job timeline.
- **Provider console:** register or manage nodes, view compatible jobs, lease lifecycle, proof submission, and earnings.
- **Activity:** transaction hashes, API events, verdicts, and settlement records with clear source labels.

Do not add every section automatically. First map the current routes and add only the screens needed by the requested feature.

## Verification checklist

Run relevant checks from `frontend/package.json`:

- `npm run build` (includes API and contract artifact checks)
- `npm run lint`
- `npm run test`
- Relevant Playwright tests when routes or wallet flows change

If a check cannot run, report the exact command and reason. Do not remove or weaken checks. Review the diff for accidental changes to generated files, routes, ABI/address data, environment handling, and backend contracts.

## Completion report

Report files changed, user-visible results, preserved behavior, checks and results, remaining dependency/environment/backend/contract work, and assumptions.
