# DEMO-008 Completion Report

## Outcome

The repeatable three-device acceptance tooling is implemented and locally
verified. Final ticket acceptance remains deliberately open until Device A,
Device B, and the independent Device C execute the two funded Arbitrum Sepolia
jobs. The repository does not claim that unavailable physical evidence passed.

Delivered interfaces:

- `demo008_provider_worker_wizard.sh`: provider-only, real ResNet50/BERT CUDA
  Worker setup with isolated node credentials and start/status/stop controls.
- `demo008_three_device_acceptance_wizard.sh`: browser-led ResNet50, provider
  interruption, BERT-on-the-other-node, screenshot, evidence, and shutdown
  sequence.
- `demo008_acceptance_probe.py`: authenticated authoritative job-state
  validation that records only sanitized public IDs, fingerprints, and chain
  transaction hashes.
- `DEMO008_THREE_DEVICE_ACCEPTANCE.md`: fresh-operator setup, demonstration,
  failure recovery, evidence, and cleanup runbook.

## Acceptance state

- Code/tooling gate: **passed locally**.
- Device B real-model capability: previously demonstrated for ResNet50/BERT;
  must be repeated through this production flow.
- Independent Device C capability: **owner/friend execution required**.
- Two funded production browser journeys on distinct nodes: **required**.
- Offline/recovery screenshot and final sanitized evidence: **required**.

DEMO-008 becomes complete only when the acceptance wizard prints
`DEMO-008 acceptance passed` and the evidence file reports `status: passed`.

## Phase 6/7 Skill Usage

### Discovered Skills

- solidity-foundry-security, tdd, domain-modeling, code-review,
  diagnosing-bugs, research, codebase-design, grill-with-docs,
  improve-codebase-architecture, handoff, ask-matt,
  setup-matt-pocock-skills, teach, wizard, banner-design, brand, design,
  design-system, slides, ui-styling, ui-ux-pro-max.

### Applied Skills

1. **tdd**: Defined the public CLI seams, observed missing-command failures,
   then implemented the evidence probe and both wizards until their behavior
   tests passed.
2. **domain-modeling**: Preserved the distinctions among Demo device, GPU node,
   GPU provider, Worker, Worker signer, Verifier, Job, proof, and Settlement in
   the operator language.
3. **wizard**: Limited prompts to human-only wallet, second-device, browser,
   and credential steps; automated deterministic validation and protected
   persistence.
4. **diagnosing-bugs**: Established the acceptance probe as the tight,
   red-capable loop for incomplete settlement or same-node assignment rather
   than diagnosing from screenshots.
5. **code-review**: Standards and Spec reviews run after the implementation
   commit; medium or higher findings must be resolved before handoff.

### Not Applied

- **solidity-foundry-security**: no contract or ABI changes.
- **research**: no new external product fact was required.
- **codebase-design**: existing Worker, runner, API, and browser seams were
  sufficient; no new architectural boundary was introduced.
- **grill-with-docs**, **improve-codebase-architecture**, **handoff**,
  **ask-matt**, **setup-matt-pocock-skills**, **teach**: no new plan debate,
  broad refactor, session transfer, routing, installation, or teaching task.
- **banner-design**, **brand**, **design**, **design-system**, **slides**,
  **ui-styling**, **ui-ux-pro-max**: no frontend visual change was needed.

## Review result

The independent Standards and Spec reviews found one high- and three
medium-severity issues. All were resolved before handoff:

1. The authenticated job response now exposes sanitized attempt history, and
   the probe requires BERT to move from a failed/expired attempt to a completed
   attempt across the two declared nodes. Attempt count alone is not accepted.
2. Device B/C UUIDs are passed into the probe and must exactly equal the two
   authoritative settled-job node IDs.
3. Each provider wizard requires the same full reviewed commit, a clean tracked
   tree, and consistent submodules; the commit is retained in sanitized
   evidence.
4. Provider setup downloads only the locally required pinned BERT vocabulary.
   Runtime weights arrive through the private capability and are hash-verified
   in the Worker's existing hash-keyed cache, avoiding a discarded duplicate
   download.

Verification after these fixes:

- complete backend suite: `368 passed, 71 skipped`;
- frontend suite: `76 passed` across 16 files;
- DEMO-008 CLI/API behavior: `16 passed` in the combined focused run;
- Ruff, ESLint, ShellCheck, Bash syntax, OpenAPI/type synchronization,
  contract-artifact checks, and the production frontend build pass;
- owner-laptop provider preflight passes with NVIDIA and PyTorch CUDA access.

**Final review disposition:** pending re-review of the resolved findings. Live
three-device execution remains an explicit owner/friend acceptance gate.
