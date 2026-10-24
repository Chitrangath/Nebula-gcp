#!/usr/bin/env bash
# Browser-led three-device production acceptance with sanitized evidence.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
# shellcheck source=scripts/lib/nebula_owner_wizard.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/nebula_owner_wizard.sh"
readonly PROBE="${SCRIPT_DIR}/demo008_acceptance_probe.py"
readonly EVIDENCE="${NEBULA_GCP_EVIDENCE_DIR}/demo008-three-device.json"

show_plan() {
  printf '%s\n' \
    'DEMO-008 three-device acceptance:' \
    '  1/9 verify the reviewed deployment and direct health' \
    '  2/9 identify distinct Device B and Device C registered nodes' \
    '  3/9 start five owner runners and both provider-only real-model Workers' \
    '  4/9 complete the ResNet50 browser journey on Device A' \
    '  5/9 demonstrate provider interruption and explicit recovery' \
    '  6/9 complete the BERT browser journey on Device A using the other node' \
    '  7/9 generate sanitized acceptance evidence from authoritative job state' \
    '  8/9 capture the required browser screenshots and explorer views' \
    '  9/9 stop all controlled processes and preserve recovery commands'
}

show_help() { printf 'Usage: %s --check | --plan | --run | --help\n' "${0##*/}"; }

check_local() {
  local failed=0
  check_commands bash curl python3 git || failed=1
  for path in "$PROBE" "${SCRIPT_DIR}/demo008_provider_worker_wizard.sh" "${SCRIPT_DIR}/gcp006_laptop_demo_runtime_wizard.sh"; do
    if [[ -f "$path" ]]; then
      printf '  OK  %s\n' "${path#"${NEBULA_WIZARD_REPO_ROOT}"/}"
    else
      printf '  ERR missing %s\n' "$path" >&2; failed=1
    fi
  done
  (( failed == 0 ))
}

run_wizard() {
  require_interactive_terminal; init_owner_paths

  stage 1 9 "Verify reviewed deployment and direct health"
  check_local
  local frontend_origin api_origin
  ask_public frontend_origin "Production Vercel HTTPS origin"
  ask_public api_origin "Cloud Run API HTTPS origin"
  require_https_origin FRONTEND_URL "$frontend_origin"; require_https_origin CLOUD_RUN_ORIGIN "$api_origin"
  run_command "check Cloud Run liveness" curl --fail --silent --show-error --max-time 20 "${api_origin%/}/live"
  confirm_action "DEPLOYMENT-REVIEWED" "Confirm this production deployment contains the reviewed DEMO-001 through DEMO-007 commits."

  stage 2 9 "Identify Device B and Device C registered nodes"
  local node_b node_c
  ask_public node_b "Device B registered GPU node ID"
  ask_public node_c "Device C registered GPU node ID"
  reject_placeholder DEVICE_B_NODE_ID "$node_b"; reject_placeholder DEVICE_C_NODE_ID "$node_c"
  [[ "$node_b" != "$node_c" ]] || { printf 'Device B and Device C must use distinct node IDs.\n' >&2; return 1; }
  confirm_action "TWO-PROVIDERS-READY" "On each GPU laptop, run demo008_provider_worker_wizard.sh --run with that node's own API key and Worker signer."

  stage 3 9 "Start controlled owner runners and verify both Workers"
  printf 'Owner laptop: %s --run (start the five runners; do not use its fixture Worker).\n' "${SCRIPT_DIR}/gcp006_laptop_demo_runtime_wizard.sh"
  printf 'Both GPU laptops: %s --status\n' "${SCRIPT_DIR}/demo008_provider_worker_wizard.sh"
  confirm_action "RUNTIME-HEALTHY" "Confirm all five owner runners and both provider-only Workers are RUNNING, and /network shows both nodes online."

  stage 4 9 "Complete ResNet50 browser journey on Device A"
  open_url "$frontend_origin"
  local resnet_job resnet_node
  ask_public resnet_job "Completed ResNet50 job UUID shown in the browser"
  ask_public resnet_node "ResNet50 assigned node UUID shown in the browser"
  [[ "$resnet_node" == "$node_b" || "$resnet_node" == "$node_c" ]] || { printf 'ResNet50 was not assigned to Device B or C.\n' >&2; return 1; }

  stage 5 9 "Demonstrate provider interruption and explicit recovery"
  printf 'Stop the provider that did NOT run ResNet50 and wait until /network shows only the ResNet provider online.\n'
  printf 'Submit the BERT job, wait until it is assigned to the ResNet provider, then stop that Worker before completion. Immediately restart the other provider.\n'
  confirm_action "RETRY-OBSERVED" "Confirm the BERT page showed retry/reassignment (at least two attempts) after the assigned provider stopped."

  stage 6 9 "Complete BERT browser journey on Device A using the other node"
  local bert_job bert_node
  ask_public bert_job "Completed BERT job UUID shown in the browser"
  ask_public bert_node "BERT assigned node UUID shown in the browser"
  [[ "$bert_node" == "$node_b" || "$bert_node" == "$node_c" ]] || { printf 'BERT was not assigned to Device B or C.\n' >&2; return 1; }
  [[ "$bert_node" != "$resnet_node" ]] || { printf 'BERT must demonstrate assignment to the other provider node.\n' >&2; return 1; }

  stage 7 9 "Generate sanitized acceptance evidence"
  local access_token
  ask_secret access_token "Fresh Device A access token (kept only in this process)"
  DEMO008_ACCESS_TOKEN="$access_token" run_command "validate two authoritative settled journeys" \
    python3 "$PROBE" --api-origin "$api_origin" --resnet-job "$resnet_job" --bert-job "$bert_job" --output "$EVIDENCE"
  unset access_token DEMO008_ACCESS_TOKEN

  stage 8 9 "Capture screenshots and independent explorer evidence"
  printf 'Capture: ResNet result, BERT result, /network with both devices, interrupted offline state, both provider dashboards, and all displayed Arbiscan transaction pages.\n'
  printf 'Never capture access tokens, cookies, API keys, private keys, signed URLs, database URLs, or terminal secret entry.\n'
  confirm_action "SANITIZED-SCREENSHOTS-SAVED" "Confirm the required screenshots contain no credentials."

  stage 9 9 "Restore and stop controlled processes"
  printf 'Restart the interrupted provider with demo008_provider_worker_wizard.sh --run if another demonstration follows.\n'
  printf 'After the demonstration, run on both GPU devices: demo008_provider_worker_wizard.sh --stop\n'
  printf 'On the owner laptop: gcp006_laptop_demo_runtime_wizard.sh --stop\n'
  confirm_action "PROCESSES-STOPPED" "Confirm both Workers and all five controlled runners are stopped now."
  printf 'DEMO-008 acceptance passed. Sanitized evidence: %s\n' "$EVIDENCE"
}

main() {
  case "${1:-}" in
    --check) [[ $# -eq 1 ]] && check_local ;;
    --plan) [[ $# -eq 1 ]] && show_plan ;;
    --run) [[ $# -eq 1 ]] && run_wizard ;;
    --help|-h) show_help ;;
    *) show_help >&2; return 2 ;;
  esac
}

main "$@"
