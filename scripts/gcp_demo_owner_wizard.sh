#!/usr/bin/env bash
# GCP-003 owner wizard design: local checks and future-stage planning only.

set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly SERVICE_TEMPLATE="${REPO_ROOT}/deploy/gcp-demo/cloud-run-service.template.yaml"
readonly REWRITE_TEMPLATE="${REPO_ROOT}/deploy/gcp-demo/vercel-rewrite.template.json"
readonly VALIDATOR="${REPO_ROOT}/scripts/validate_gcp_demo_config.py"

refuse_xtrace() {
  if [[ "$-" == *x* ]]; then
    printf 'Refusing to run while shell xtrace is enabled. Disable xtrace first.\n' >&2
    exit 2
  fi
}

show_plan() {
  printf '%s\n' \
    'GCP-003 future owner stages (design only; not executable in this ticket):' \
    '  1/13 project, region, and billing approval' \
    '  2/13 budget alerts and cost review' \
    '  3/13 required API enablement' \
    '  4/13 private durable-storage bucket provisioning' \
    '  5/13 least-privilege IAM and bucket-scoped object token' \
    '  6/13 secret creation with pinned versions' \
    '  7/13 immutable image review' \
    '  8/13 Cloud Run deployment' \
    '  9/13 public /live and database-backed /ready' \
    '  10/13 cross-runtime private storage acceptance' \
    '  11/13 Vercel same-origin rewrite cutover' \
    '  12/13 real browser authentication smoke' \
    '  13/13 rollback and OCI switch-back' \
    '' \
    'Every future external stage requires immediate owner confirmation.' \
    'No action was performed.'
}

check_local_prerequisites() {
  local failed=0
  printf 'GCP-003 local prerequisite check\n'
  for command_name in bash python3 git; do
    if command -v "$command_name" >/dev/null 2>&1; then
      printf '  OK  %s is available\n' "$command_name"
    else
      printf '  ERR %s is required\n' "$command_name" >&2
      failed=1
    fi
  done
  if command -v docker >/dev/null 2>&1; then
    printf '  OK  docker CLI is available (daemon was not contacted)\n'
  else
    printf '  WARN docker CLI is absent; it is required only for a later local image check\n'
  fi

  for required_file in "$SERVICE_TEMPLATE" "$REWRITE_TEMPLATE" "$VALIDATOR" "${REPO_ROOT}/backend/Dockerfile"; do
    if [[ -f "$required_file" ]]; then
      printf '  OK  %s exists\n' "${required_file#"${REPO_ROOT}/"}"
    else
      printf '  ERR %s is missing\n' "${required_file#"${REPO_ROOT}/"}" >&2
      failed=1
    fi
  done
  if [[ -d "${REPO_ROOT}/.git-local" ]] && git --git-dir="${REPO_ROOT}/.git-local" --work-tree="$REPO_ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
    printf '  OK  independent .git-local repository is usable\n'
  else
    printf '  ERR independent .git-local repository is unavailable\n' >&2
    failed=1
  fi
  if (( failed )); then
    return 1
  fi
  python3 "$VALIDATOR" --template --service "$SERVICE_TEMPLATE" --rewrite "$REWRITE_TEMPLATE"
  printf 'No account, network, credential, build, upload, or deployment action was performed.\n'
}

usage() {
  printf 'Usage: %s --check | --plan\n' "${0##*/}"
}

main() {
  refuse_xtrace
  case "${1:-}" in
    --check)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      check_local_prerequisites
      ;;
    --plan)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      show_plan
      ;;
    --help|-h)
      usage
      ;;
    *)
      printf 'GCP-003 is local planning only; external actions are intentionally unavailable.\n' >&2
      usage >&2
      return 2
      ;;
  esac
}

main "$@"
