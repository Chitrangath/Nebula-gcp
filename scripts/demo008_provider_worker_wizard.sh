#!/usr/bin/env bash
# Provider-only real-model Worker setup for one DEMO-008 GPU laptop.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
# shellcheck source=scripts/lib/nebula_owner_wizard.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/nebula_owner_wizard.sh"

readonly PROVIDER_DIR="${NEBULA_GCP_STATE_DIR}/demo008-provider"
readonly PROVIDER_ENV="${NEBULA_GCP_CONFIG_DIR}/demo008-provider-worker.env"
readonly PID_FILE="${PROVIDER_DIR}/worker.pid"
readonly LOG_FILE="${PROVIDER_DIR}/worker.log"

show_plan() {
  printf '%s\n' \
    'DEMO-008 provider-only GPU Worker:' \
    '  1/5 validate the GPU, repository, and Worker environment' \
    '  2/5 download and verify the pinned BERT vocabulary and weights' \
    '  3/5 capture this node API key and Worker signer without exposing either' \
    '  4/5 prepare a CUDA Worker for real ResNet50 and BERT execution' \
    '  5/5 start one provider-only Worker with status and stop controls' \
    '' \
    'This wizard never starts backend runners and never requests database, R2, Verifier, or AI-user secrets.'
}

show_help() { printf 'Usage: %s --check | --plan | --run | --status | --stop | --help\n' "${0##*/}"; }

check_local() {
  local failed=0
  check_commands bash python3 nvidia-smi || failed=1
  if [[ -x "${NEBULA_WIZARD_REPO_ROOT}/worker/.venv/bin/python" ]]; then
    printf '  OK  worker Python environment\n'
  else
    printf '  ERR worker virtual environment is missing\n' >&2; failed=1
  fi
  if "${NEBULA_WIZARD_REPO_ROOT}/worker/.venv/bin/python" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' 2>/dev/null; then
    printf '  OK  PyTorch CUDA\n'
  else
    printf '  ERR PyTorch cannot use CUDA\n' >&2; failed=1
  fi
  (( failed == 0 ))
}

show_status() {
  if [[ -f "$PID_FILE" ]]; then
    local pid; pid=$(<"$PID_FILE")
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      printf 'RUNNING worker pid=%s\n' "$pid"; return 0
    fi
    printf 'STOPPED worker stale_pid=%s\n' "$pid"; return 1
  fi
  printf 'STOPPED worker\n'; return 1
}

stop_worker() {
  [[ -f "$PID_FILE" ]] || { printf 'No provider Worker is recorded.\n'; return 0; }
  local pid; pid=$(<"$PID_FILE")
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid"; printf 'Sent TERM to provider Worker pid=%s.\n' "$pid"
  fi
  rm -f -- "$PID_FILE"
}

write_assignment() {
  local name="$1" value="$2"
  printf '%s=%q\n' "$name" "$value" >> "$PROVIDER_ENV"
}

run_wizard() {
  require_interactive_terminal
  init_owner_paths

  stage 1 5 "Validate GPU, repository, and Worker environment"
  check_local

  stage 2 5 "Acquire and independently verify pinned BERT artifacts"
  local model_dir="${NEBULA_GCP_STATE_DIR}/models/bert-base"
  confirm_action "PREPARE-BERT" "Download or verify the pinned BERT release in the protected local model cache?"
  run_command "prepare pinned BERT model" "${NEBULA_WIZARD_REPO_ROOT}/worker/.venv/bin/python" "${NEBULA_WIZARD_REPO_ROOT}/scripts/prepare_bert_model.py" --output-dir "$model_dir"
  [[ -s "${model_dir}/vocab.txt" && -s "${model_dir}/model.safetensors" ]] || { printf 'Verified BERT artifacts are missing.\n' >&2; return 1; }

  stage 3 5 "Capture node identity and Worker credentials"
  local api_origin contract node_id api_key signing_key resnet_url
  ask_public api_origin "Cloud Run API HTTPS origin"
  ask_public contract "NebulaPayment contract address"
  ask_public node_id "This laptop registered GPU node ID"
  ask_secret api_key "This node API key"
  ask_secret signing_key "This node Worker signer private key"
  ask_public resnet_url "Owner-approved immutable ResNet50 artifact HTTPS URL"
  require_https_origin CLOUD_RUN_ORIGIN "$api_origin"
  reject_placeholder NODE_ID "$node_id"; reject_placeholder API_KEY "$api_key"; reject_placeholder WORKER_SIGNING_PRIVATE_KEY "$signing_key"; reject_placeholder MODEL_ARTIFACT_URL "$resnet_url"
  confirm_action "PROVIDER-CREDENTIALS-REVIEWED" "Confirm this API key and signer belong only to the displayed node and were not pasted into chat."

  stage 4 5 "Prepare a real CUDA multimodel Worker"
  mkdir -p "$PROVIDER_DIR"; chmod 700 "$PROVIDER_DIR"
  : > "$PROVIDER_ENV"; chmod 600 "$PROVIDER_ENV"
  write_assignment NODE_ID "$node_id"
  write_assignment API_KEY "$api_key"
  write_assignment WORKER_SIGNING_PRIVATE_KEY "$signing_key"
  write_assignment BACKEND_URL "${api_origin%/}"
  write_assignment VERIFYING_CONTRACT "$contract"
  write_assignment EXECUTOR_ADAPTER multimodel
  write_assignment EXECUTOR_DEVICE cuda
  write_assignment BERT_VOCAB_PATH "${model_dir}/vocab.txt"
  write_assignment MODEL_ARTIFACT_URL "$resnet_url"
  write_assignment MODEL_CACHE_DIR "${NEBULA_GCP_STATE_DIR}/models/cache"
  write_assignment CHAIN_ID 421614

  stage 5 5 "Start one provider-only Worker"
  confirm_action "START-PROVIDER-WORKER" "Start this real-model Worker now?"
  if [[ -f "$PID_FILE" ]] && kill -0 "$(<"$PID_FILE")" 2>/dev/null; then
    printf 'Refusing to start a duplicate Worker.\n' >&2; return 1
  fi
  (
    set -a
    # shellcheck disable=SC1090
    source "$PROVIDER_ENV"
    set +a
    cd "${NEBULA_WIZARD_REPO_ROOT}/worker"
    exec .venv/bin/python worker.py
  ) > "$LOG_FILE" 2>&1 &
  printf '%s\n' "$!" > "$PID_FILE"; chmod 600 "$PID_FILE"
  printf 'Started provider-only Worker pid=%s.\nStatus: %s --status\nStop: %s --stop\n' "$!" "$0" "$0"
}

main() {
  case "${1:-}" in
    --check) [[ $# -eq 1 ]] && check_local ;;
    --plan) [[ $# -eq 1 ]] && show_plan ;;
    --run) [[ $# -eq 1 ]] && run_wizard ;;
    --status) [[ $# -eq 1 ]] && show_status ;;
    --stop) [[ $# -eq 1 ]] && stop_worker ;;
    --help|-h) show_help ;;
    *) show_help >&2; return 2 ;;
  esac
}

main "$@"
