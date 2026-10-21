# BE-002 Zero-Cost Hosting Options

**Research date:** 2026-09-27
**Decision scope:** Replace the stopped Fly.io deployment path with services that can remain at $0. The required system is a public HTTPS Python/FastAPI Docker backend, async PostgreSQL, a same-origin frontend `/api/v1/*` proxy, and the Phase 3 receipt, assignment, settlement, event, and reconciliation runners.

## Executive conclusion

Fly.io is not eligible: its free offer is only a trial lasting **2 total VM hours or 7 days**, whichever comes first. Trial machines stop after five minutes, and adding a card ends the trial and starts normal billing. ([Fly.io free-trial documentation](https://fly.io/docs/about/free-trial/))

No cardless managed host evaluated here simultaneously supplies all of the following indefinitely at $0:

- a stable public HTTPS Docker service;
- an always-running FastAPI process;
- CPU for five continuous background runners; and
- durable PostgreSQL.

The best fit for the existing architecture is:

1. **Oracle Cloud Infrastructure Always Free VM** for the backend and continuous runners;
2. **Supabase Free** for PostgreSQL; and
3. **Vercel Hobby** for the Vite frontend only if the project remains personal/non-commercial.

This path has no required paid compute, but Oracle normally requires a credit/debit card for identity verification. Oracle says the card is not charged unless the account is explicitly upgraded. Always Free resources remain available after the trial. ([Oracle Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm))

If **no card at all** is acceptable, the practical hosted alternative is Render Free plus Supabase Free. That is suitable for demonstrations, not the existing continuous runtime: Render sleeps after 15 minutes without inbound traffic and does not provide a free background-worker service. BE-002 must not be declared production-complete under that topology unless the five runners are deliberately redesigned as externally triggered, idempotent ticks and the cold-start/delay semantics are accepted.

## Provider comparison

| Service | Zero-cost status and billing exposure | Relevant limits | Continuous Nebula runners | Decision |
|---|---|---|---|---|
| **Fly.io** | Trial only: 2 VM hours or 7 days. Adding a card ends the trial. | Trial machines auto-stop after 5 minutes. | No permanent free compute. | **Reject.** |
| **Render Free** | A free web-service plan exists. Without a payment method, over-limit services are suspended instead of billed. | 512 MB class; 750 free instance-hours per workspace/month; sleeps after 15 idle minutes; about a one-minute cold start; ephemeral disk. Render Free Postgres expires after 30 days. | No. Free background workers are unavailable and an in-process runner stops when the web service sleeps. | **Cardless demo option only.** Use Supabase, not Render Postgres. |
| **Koyeb Free** | One free web instance, but Koyeb's Starter organization requires a valid payment method and is pay-as-you-go outside the free instance. | 0.1 vCPU, 512 MB RAM, 2 GB SSD; Frankfurt or Washington only; sleeps after one idle hour; no volume, custom scaling, or Worker Service. | No. Free instances cannot be Worker Services and must scale to zero. | **Reject for full runtime.** |
| **Google Cloud Run** | Monthly Free Tier has no end date, but a Cloud Billing account is required; paid billing accounts are charged beyond allowance. | Request-based allowance includes 2 million requests, 180,000 vCPU-seconds, 360,000 GiB-seconds, and 1 GiB North America egress/month. | Not in request-based mode: CPU is allocated only during requests. Instance-based billing supports background work but charges for the lifecycle; minimum instances incur cost. | **Reject for unchanged runtime.** Possible only after event-driven redesign and with billing exposure. |
| **Oracle OCI Always Free** | Always Free resources have no expiry. Most sign-ups require a phone and card, but Oracle says the card is not charged unless the account is explicitly upgraded. | The selected Nebula profile is 1 OCPU/6 GB on A1 Flex; this leaves headroom within the account allowance but is intentionally low-throughput. Home-region capacity applies. Idle VMs may be reclaimed when CPU and network—and, for A1, memory—remain under 20% during a 7-day period. | Yes for the low-traffic control plane; validate runner throughput before enabling all runners. | **Recommended for testnet staging**, subject to card verification, capacity, reclamation, and load-test results. |
| **Supabase Free** | $0 plan, two active projects. | 500 MB database size, 5 GB egress; inactive projects may pause after 7 days. A few real DB queries per day typically prevent inactivity pausing. | Database only; not a backend host. | **Recommended PostgreSQL**, within quota. |
| **Vercel Hobby** | $0 with no billing cycle; projects pause when included usage is exhausted. | Personal/non-commercial use only. Includes HTTPS and static deployments. | Frontend only. | **Accept for a personal/non-commercial testnet frontend.** Reassess before commercial use. |
| **Cloudflare Tunnel + self-hosting** | Tunnel is available on free plans, but it supplies connectivity, not compute. | A named production tunnel requires a Cloudflare account, a domain on Cloudflare, and an owner-operated server. Quick Tunnels are explicitly for development/testing. | Yes only while the owner's computer/server, network, Docker stack, and tunnel stay online. | **No-host-bill fallback**, not unattended managed hosting. |

### Primary sources

- Fly.io: [free trial](https://fly.io/docs/about/free-trial/) and [pricing](https://fly.io/docs/about/pricing/).
- Render: [free-service limits](https://render.com/docs/free), [billing behavior without a payment method](https://render.com/docs/faq), and [background workers](https://render.com/docs/background-workers).
- Koyeb: [free instance limits](https://www.koyeb.com/docs/reference/instances), [scale to zero](https://www.koyeb.com/docs/run-and-scale/scale-to-zero), and [Starter payment-method requirement](https://www.koyeb.com/docs/reference/organizations).
- Google Cloud: [Cloud Run Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features), [Cloud Run pricing](https://cloud.google.com/run/pricing), [CPU/billing behavior](https://docs.cloud.google.com/run/docs/configuring/billing-settings), and [background-thread guidance](https://docs.cloud.google.com/run/docs/tips/general).
- Oracle: [Free Tier account and card behavior](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), [Always Free compute/network limits and idle reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [public IP lifetimes](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm), and [reserving an existing public IPv4](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/reserved-ipv4-reserving-existing-ipv4-address.htm).
- Supabase: [Free plan quotas](https://supabase.com/docs/guides/platform/billing-on-supabase), [project pausing](https://supabase.com/docs/guides/platform/free-project-pausing), and [PostgreSQL connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres).
- Vercel: [Hobby plan](https://vercel.com/docs/plans/hobby), [plan behavior at quota](https://vercel.com/docs/plans), and [terms restricting Hobby to personal/non-commercial use](https://vercel.com/legal/terms).
- Cloudflare: [Tunnel availability and behavior](https://developers.cloudflare.com/tunnel/), [production-tunnel prerequisites](https://developers.cloudflare.com/tunnel/get-started/), [Quick Tunnel limitations](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/), and [Zero Trust Free pricing](https://www.cloudflare.com/plans/zero-trust-services/).

## Architecture implications

### Option A — preserve the Phase 3 runtime: Oracle Always Free

This is the only evaluated hosted $0 allowance that matches the current long-running process model.

- Run the FastAPI container and five bounded loops defined in `backend/app/runners.py`: `receipts`, `assignment`, `settlement`, `events`, and `reconciliation`.
- Use a process supervisor or Docker Compose with one API service and runner services. Restarts must be automatic and secrets must be injected at runtime, never stored in the image or repository.
- Keep the Oracle tenancy as a **Free Tier account**; do not press **Upgrade** or create any resource unless the console marks it **Always Free eligible**.
- Use the selected 1-OCPU/6-GB A1 allocation for the low-traffic control plane. The implementation subsequently built the locked backend image successfully for `linux/arm64`, and the owner wizard verifies `aarch64`, exactly 1 OCPU, and approximately 6 GB RAM before deployment.
- Use Supabase's IPv6 direct connection for a persistent backend when available. Otherwise use the shared **session** pooler on port 5432. Do not substitute the transaction pooler on port 6543 without verifying SQLAlchemy prepared-statement/session behavior; Supabase documents transaction-mode limitations.
- Keep Vercel's `/api/v1/:path*` rewrite pointed at the Oracle HTTPS backend so authentication cookies remain first-party to the frontend origin. The backend should not be called cross-origin from browser code.
- Add TLS in front of the OCI service. This implementation uses Caddy and a DuckDNS hostname mapped to an OCI **reserved** public IPv4. Oracle documents that ephemeral IP objects are temporary while reserved public IP objects persist beyond an instance and can be reassigned. The owner wizard independently confirms the console's cost estimate remains zero before accepting the address.
- Configure external health monitoring and backups. Oracle explicitly reserves the right to reclaim idle Always Free instances; an actual workload and monitoring reduce surprise but do not remove that platform risk.

This is zero-cost only while all resources remain within their Always Free/Free quotas. It is not a production SLA.

### Option B — no card: Render Free demonstration topology

Render can run the existing Docker web API publicly with managed TLS, and Supabase supplies durable PostgreSQL. Vercel can keep the same-origin proxy. However:

- the backend sleeps after 15 minutes without inbound HTTP or WebSocket traffic;
- internal scheduler activity does not count as inbound traffic;
- there is no free Render background-worker instance; and
- cold start may delay the first request by about a minute.

Do not evade the sleep policy with artificial keep-alive traffic. If this path is chosen, make a scoped architecture change instead:

1. expose authenticated, idempotent maintenance endpoints or a single orchestrator endpoint;
2. run the current `--once` operations when that endpoint is invoked;
3. authenticate scheduler calls independently of browser JWTs;
4. add overlap protection/advisory locking and preserve current outbox/idempotency guarantees;
5. invoke the endpoint using a legitimate scheduler; and
6. explicitly accept scheduling delay, cold starts, missed-tick recovery, and lack of continuous settlement/event polling.

Cloud Scheduler is not a cardless escape hatch: it provides three jobs per billing account at no charge, but Google Cloud requires a billing account and overage remains possible. ([Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)) The backend currently has five runner types, so using at most three free scheduled jobs would also require consolidating them safely.

## Decision and implementation status

The owner selected policy 1 below. The Fly wizard has been replaced with the
reviewed OCI owner wizard; the other options remain documented only as rejected
fallbacks.

1. **Selected — card verification is acceptable, but automatic charges are not:** use Oracle Always Free + Supabase Free + Vercel Hobby (only while non-commercial). The owner wizard verifies that the Oracle account remains un-upgraded and every OCI resource is labelled Always Free eligible with a zero-cost estimate.
2. **No card and no billing account are acceptable:** use Render Free + Supabase Free only as a demonstration deployment and authorize the runner-trigger redesign before implementation.
3. **No card, no architecture change, and an always-on owner-controlled machine is available:** self-host the Docker stack behind a named Cloudflare Tunnel, accepting local power/network/maintenance as infrastructure dependencies.

There is no honest fourth choice in the evaluated set that is simultaneously cardless, managed, continuously running, production-like, and permanently $0.

## BE-002 closure rule

BE-002 must remain partial until the selected replacement topology passes the existing real-browser authentication smoke test through the final frontend origin. Broader Phase 3 deployment is not complete until all five runners execute reliably under the chosen topology and event reconciliation reaches the expected on-chain state. A green API authentication test alone does not prove scheduler/settlement continuity.
