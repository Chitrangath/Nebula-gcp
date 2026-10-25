# Live Arbitrum Sepolia end-to-end verification — 2026-10-25

## Tested deployment

- Frontend: `https://nebula-gcp.vercel.app` (currently deployed version).
- API: `https://nebula-api-93573724992.asia-south1.run.app` on Cloud Run.
- Database: hosted PostgreSQL at Alembic head `0010_node_bert_capability`.
- Private storage: Cloudflare R2, accessed through the authenticated result API.
- Chain: Arbitrum Sepolia (`421614`), contract `0xbD0A2f65ae2C67A313d2883cAed5029A3275a599`.
- Execution: approved SHA-256 verified ResNet50 artifact on an NVIDIA RTX 3050 laptop GPU, with temporary laptop Worker and five backend runners.

The deployed frontend returned 200, its same-origin `/api/live` route returned 200, and Cloud Run `/live` and `/ready` both returned 200. The deployed Chromium browser-auth smoke passed. The AI-user wallet then authenticated through the Vercel `/api/v1/*` route, and both job details and result downloads succeeded through that same route.

## Live jobs and chain evidence

| Job | Escrow | Assignment | Proof | Settlement | Final state |
| --- | --- | --- | --- | --- | --- |
| `45ba2811-b3d2-5067-9f47-b09b5768d509` | `0xf21cead6982c236899284d63641b496597aa1009c808be011dd47725f0c0d583` | `0x058a743adcf345fbe5b2aa1e7eed1b34a9c29bfbdb9d077e47006f92617b28e7` | `0xb25a1033c4797a5788431d6d15d70c9f00dbbf4dd278f3af09987e084d9e065e` | `0x7a7d4862f6d4c13e859b77cac83b75908b5e448d0af3678f45d77ea84c1a42b4` | Completed, reconciled, valid proof |
| `f2d9df25-0260-5e85-8870-f2778c6c1f14` | `0x5a02356cc3e804dd6b882b49f45c08c98566a662dbcfd9f305130419a12aab58` | `0x95cafc60179fed75acf9099e3379589eb730507503e2eddeed543c9a86ded630` | `0xa9eb1fd2b77b0296541b7a96c0363ac55e83f5e1967859bdb240f2aadde5a565` | `0xbe5cace3b68dfd1796cdee77e18d3c70db9a36e494b189a8364615535871c903` | Completed, reconciled, valid proof |

All eight transaction receipts independently returned status 1. Both contract job states are `4` (settled). Both authenticated result downloads returned 200, 309 bytes, and SHA-256 `edbf766993c176f80f88db438d8eaad36245c8b9db60dc062e81aa0bfbcf290c`.

The provider withdrawal transaction `0x1f69adc09b2773e5c5c01d212d7dfe4ba241619955c5d6b0aac6f033aa2e899f` succeeded in block `322797136`. Its USDC `Transfer` event moved **200,000 base units (0.20 test USDC)** from the contract to the provider: 100,000 from the two new jobs plus 100,000 already pending before this run. The contract now reports zero pending withdrawal, and the hosted payment rows for both new jobs are `withdrawn` with this transaction hash.

## Probe repair and evidence limit

The funded journey reached both settlements and the provider withdrawal, but the outer GCP-004 wrapper failed afterward while saving stderr: it tried to `chmod /tmp`, which is a shared directory and was rejected. This discarded the child's JSON summary, so its own final exit status is unavailable. No duplicate funded probe was run. The job, result, proof, receipt, and withdrawal findings above were reconstructed independently through read-only hosted API, database, and chain queries.

The wrapper now leaves existing parent-directory permissions intact while setting its diagnostic file to mode 0600. A regression test reproduced the old permission change and passed after the fix. The live probe also now preserves existing approved model metadata; the production ResNet50 upload limit remained 25 MB. A mismatched model artifact fails before live writes.

After the run, the exact temporary probe, Worker, and runner process IDs were absent. Targeted and full script regression checks passed: **37 targeted tests**, then **95 script tests**, plus Ruff and `git diff --check`.

This verifies the currently deployed frontend route, browser authentication, hosted API, one real GPU model, private result retrieval, chain settlement, and withdrawal. It does not verify the uncommitted frontend redesign in this worktree, a second GPU device, BERT execution, or an interactive MetaMask confirmation in a human browser.

## Skill usage

Repository skills discovered: `ask-matt`, `banner-design`, `brand`, `code-review`, `codebase-design`, `custom-ui-nebula`, `design`, `design-system`, `diagnosing-bugs`, `domain-modeling`, `grill-with-docs`, `handoff`, `improve-codebase-architecture`, `research`, `setup-matt-pocock-skills`, `slides`, `solidity-foundry-security`, `tdd`, `teach`, `ui-styling`, `ui-ux-pro-max`, `wizard`.

Applied `diagnosing-bugs` to reproduce the wrapper failure and reconstruct its masked outcome; `tdd` to lock down the shared-directory and model-registry regressions; `custom-ui-nebula` to preserve the same-origin wallet/API boundary in deployed frontend checks; and `solidity-foundry-security` to independently check role, settlement, receipts, and provider-credit conservation. `CONTEXT.md` supplied the job, Worker, verifier, proof, and settlement vocabulary; no domain-model change was made. The other skills were outside this live verification and repair phase.
