#!/usr/bin/env bash
# Owner-guided Vercel same-origin cutover after accepted GCP-004 evidence.

set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/nebula_owner_wizard.sh
source "${SCRIPT_DIR}/lib/nebula_owner_wizard.sh"

readonly FOUNDATION_EVIDENCE="${NEBULA_GCP_EVIDENCE_DIR}/GCP004_DIRECT_ACCEPTANCE.env"
readonly REWRITE_TEMPLATE="${NEBULA_WIZARD_REPO_ROOT}/deploy/gcp-demo/vercel-rewrite.template.json"
readonly VALIDATOR="${NEBULA_WIZARD_REPO_ROOT}/scripts/validate_gcp_demo_config.py"
readonly RENDERER="${NEBULA_WIZARD_REPO_ROOT}/scripts/render_gcp_demo_config.py"
readonly MATERIALIZED_SERVICE="${NEBULA_GCP_STATE_DIR}/cloud-run-service.owner.json"
readonly MATERIALIZED_REWRITE="${NEBULA_GCP_STATE_DIR}/vercel-rewrite.owner.json"
STAGING_DIR=""

cleanup_staging() {
  [[ -z "${STAGING_DIR:-}" ]] || rm -rf -- "$STAGING_DIR"
}

trap cleanup_staging EXIT

show_plan() {
  printf '%s\n' \
    'GCP-005 later Vercel/browser cutover:' \
    '  1/7 verify GCP-004 sanitized direct acceptance evidence and real Cloud Run HTTPS origin' \
    '  2/7 verify exact frontend production origin' \
    '  3/7 render and validate reviewed same-origin /api/v1/* rewrite from the actual Cloud Run origin' \
    '  4/7 owner confirmation before Vercel mutation' \
    '  5/7 validated Vercel frontend deployment' \
    '  6/7 real browser authentication acceptance: challenge, verify, secure refresh cookie, refresh, logout, wrong/missing Origin rejection' \
    '  7/7 immediate frontend routing rollback to the prior production deployment' \
    '' \
    'Invariants: module-memory access token; HttpOnly, Secure, SameSite=Strict refresh cookie; exact Origin == FRONTEND_URL; no direct cross-origin browser API design.'
}

show_help() { printf 'Usage: %s --check | --plan | --validate-evidence | --run | --help\n' "${0##*/}"; }

check_local() {
  local failed=0
  printf 'GCP-005 local-only prerequisite check\n'
  check_commands bash python3 git || failed=1
  for optional in vercel curl; do
    command -v "$optional" >/dev/null 2>&1 && printf '  OK  %s\n' "$optional" || printf '  WARN %s is required only for later --run\n' "$optional"
  done
  [[ -f "$REWRITE_TEMPLATE" && -f "$VALIDATOR" && -f "$RENDERER" ]] || failed=1
  (( failed == 0 ))
}

evidence_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$FOUNDATION_EVIDENCE" | tail -n 1
}

validate_foundation_evidence() {
  if [[ ! -f "$FOUNDATION_EVIDENCE" ]]; then
    printf 'Refusing: GCP-004 sanitized direct acceptance evidence is missing at %s.\n' "$FOUNDATION_EVIDENCE" >&2
    return 1
  fi
  local status origin runners storage public_r2
  status=$(evidence_value STATUS); origin=$(evidence_value CLOUD_RUN_ORIGIN)
  runners=$(evidence_value RUNNERS_ENABLED); storage=$(evidence_value STORAGE_ADAPTER); public_r2=$(evidence_value PUBLIC_R2)
  require_exact STATUS accepted "$status"
  require_https_origin CLOUD_RUN_ORIGIN "$origin"
  require_exact RUNNERS_ENABLED false "$runners"
  require_exact STORAGE_ADAPTER s3 "$storage"
  require_exact PUBLIC_R2 false "$public_r2"
  printf 'GCP-004 sanitized direct acceptance evidence is valid.\n'
}

run_wizard() {
  require_interactive_terminal
  init_owner_paths

  stage 1 7 "Verify GCP-004 evidence and the real Cloud Run HTTPS origin"
  open_url "https://cloud.google.com/run/docs/managing/services"
  validate_foundation_evidence
  local cloud_run_origin
  cloud_run_origin=$(evidence_value CLOUD_RUN_ORIGIN)
  printf 'Re-run direct /live and /ready checks before routing browser traffic.\n'
  confirm_action "DIRECT-ACCEPTANCE-RECONFIRMED" "Confirm the exact recorded Cloud Run origin still passes direct acceptance."

  stage 2 7 "Verify the exact frontend production origin"
  open_url "https://vercel.com/dashboard"
  open_url "https://vercel.com/docs/domains/working-with-domains"
  local frontend_origin
  ask_public frontend_origin "Exact Vercel frontend production HTTPS origin"
  require_https_origin FRONTEND_URL "$frontend_origin"
  local configured_frontend
  configured_frontend=$(load_value FRONTEND_URL)
  require_exact FRONTEND_URL "$configured_frontend" "$frontend_origin"

  stage 3 7 "Render and validate the reviewed same-origin rewrite"
  open_url "https://vercel.com/docs/rewrites"
  save_value CLOUD_RUN_ORIGIN "$cloud_run_origin"
  python3 "$RENDERER" --config-dir "$NEBULA_GCP_CONFIG_DIR" --rewrite-output "$MATERIALIZED_REWRITE"
  python3 "$VALIDATOR" --service "$MATERIALIZED_SERVICE" --rewrite "$MATERIALIZED_REWRITE"
  printf 'The browser remains on /api/v1/*; no direct cross-origin API origin is exposed to frontend code.\n'

  stage 4 7 "Require owner confirmation before changing Vercel"
  open_url "https://vercel.com/docs/deployments/managing-deployments"
  local prior_deployment
  ask_public prior_deployment "Current known-good Vercel production deployment URL for rollback"
  require_https_origin PRIOR_VERCEL_DEPLOYMENT "$prior_deployment"
  save_value PRIOR_VERCEL_DEPLOYMENT "$prior_deployment"
  confirm_action "CUTOVER-APPROVED" "Approve the validated rewrite and a new production deployment now?"

  stage 5 7 "Deploy/redeploy the Vercel frontend only after rewrite validation"
  local staging_dir
  staging_dir=$(mktemp -d)
  STAGING_DIR="$staging_dir"
  git -C "${NEBULA_WIZARD_REPO_ROOT}" archive --format=tar HEAD frontend > "${staging_dir}/frontend.tar"
  tar -xf "${staging_dir}/frontend.tar" -C "$staging_dir"
  rm -f -- "${staging_dir}/frontend.tar"
  cp "$MATERIALIZED_REWRITE" "$staging_dir/frontend/vercel.json"
  confirm_action "DEPLOY-VERCEL" "Deploy the isolated reviewed frontend copy to production?"
  run_command "deploy validated Vercel frontend" vercel deploy --prod --cwd "$staging_dir"

  stage 6 7 "Run genuine browser authentication acceptance"
  open_url "$frontend_origin"
  printf '%s\n' \
    'In a real browser, verify challenge issuance, wallet verify, and an access token retained only in module memory.' \
    'Inspect the refresh cookie: HttpOnly, Secure, SameSite=Strict, host-only, Path=/api/v1/auth.' \
    'Verify refresh rotation, logout/revocation, and rejection of wrong and missing Origin.'
  confirm_action "BROWSER-AUTH-ACCEPTED" "Confirm every browser-auth check passed without copying tokens or cookies into evidence."
  record_public_evidence GCP005_BROWSER_CUTOVER.env "STATUS=accepted
CLOUD_RUN_ORIGIN=${cloud_run_origin}
FRONTEND_ORIGIN=${frontend_origin}
SAME_ORIGIN_API=/api/v1/*
BROWSER_AUTH=accepted"

  stage 7 7 "Provide immediate rollback to prior frontend routing"
  open_url "https://vercel.com/docs/instant-rollback"
  printf 'If any acceptance fails, stop and restore the prior production deployment immediately.\n'
  if ! confirm_action "KEEP-CUTOVER" "Keep the accepted cutover? Answering no triggers the reviewed rollback gate."; then
    confirm_action "ROLLBACK-NOW" "Roll back production to the recorded prior deployment now?" || return 2
    run_command "rollback Vercel production routing" vercel rollback "$prior_deployment"
  fi
}

main() {
  case "${1:-}" in
    --check) [[ $# -eq 1 ]] || return 2; check_local ;;
    --plan) [[ $# -eq 1 ]] || return 2; show_plan ;;
    --validate-evidence) [[ $# -eq 1 ]] || return 2; validate_foundation_evidence ;;
    --run) [[ $# -eq 1 ]] || return 2; run_wizard ;;
    --help|-h) show_help ;;
    *) show_help >&2; return 2 ;;
  esac
}

main "$@"
