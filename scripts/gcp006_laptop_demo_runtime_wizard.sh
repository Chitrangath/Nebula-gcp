#!/usr/bin/env bash
# Owner-guided laptop runtime for one supervised Nebula demonstration.

set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/nebula_owner_wizard.sh
source "${SCRIPT_DIR}/lib/nebula_owner_wizard.sh"

readonly RUNTIME_DIR="${NEBULA_GCP_STATE_DIR}/runtime"
readonly PID_DIR="${RUNTIME_DIR}/pids"
readonly LOG_DIR="${RUNTIME_DIR}/logs"
readonly BACKEND_ENV="${NEBULA_GCP_CONFIG_DIR}/laptop-backend.env"
readonly WORKER_ENV="${NEBULA_GCP_CONFIG_DIR}/laptop-worker.env"
readonly PROVIDER_WORKER_PID_FILE="${NEBULA_GCP_STATE_DIR}/demo008-provider/worker.pid"

show_plan() {
  printf '%s\n' \
    'GCP-006 supervised laptop demonstration runtime:' \
    '  1/7 validate local Docker, Python, Node, and clean configuration' \
    '  2/7 validate Cloud Run, Supabase, private R2, RPC, and contract connectivity' \
    '  3/7 validate separate worker, GPU provider, and Verifier identities' \
    '  4/7 prepare worker and five controlled runner commands' \
    '  5/7 confirm immediately before each process start' \
    '  6/7 safe status, stop, and cleanup procedure' \
    '  7/7 confirm no continuous runners on Cloud Run' \
    '' \
    'Processes are prepared but not started by default; only --run plus per-process confirmation can start them.'
}

show_help() { printf 'Usage: %s --check | --plan | --run | --status | --stop | --help\n' "${0##*/}"; }

check_local() {
  local failed=0
  printf 'GCP-006 local-only prerequisite check\n'
  check_commands bash python3 git || failed=1
  for optional in docker node npm curl; do
    command -v "$optional" >/dev/null 2>&1 && printf '  OK  %s\n' "$optional" || printf '  WARN %s is needed for the full demonstration\n' "$optional"
  done
  git -C "$NEBULA_WIZARD_REPO_ROOT" diff --quiet \
    && printf '  OK  tracked worktree is clean\n' \
    || printf '  WARN tracked worktree is dirty; --run will refuse until changes are reviewed and committed\n'
  (( failed == 0 ))
}

write_env_assignment() {
  local path="$1" name="$2" value="$3"
  [[ "$name" =~ ^[A-Z0-9_]+$ ]] || return 1
  printf '%s=%q\n' "$name" "$value" >> "$path"
  chmod 600 "$path"
}

prepare_commands() {
  mkdir -p "$RUNTIME_DIR" "$PID_DIR" "$LOG_DIR"
  chmod 700 "$RUNTIME_DIR" "$PID_DIR" "$LOG_DIR"
  local name
  for name in receipts assignment settlement events reconciliation; do
    local script_path="${RUNTIME_DIR}/${name}.sh"
    printf '#!/usr/bin/env bash\nset -euo pipefail\nset -a\nsource %q\nset +a\ncd %q\nexec .venv/bin/python -m app.runners %q\n' \
      "$BACKEND_ENV" "${NEBULA_WIZARD_REPO_ROOT}/backend" "$name" > "$script_path"
    chmod 700 "$script_path"
  done
  printf '#!/usr/bin/env bash\nset -euo pipefail\nset -a\nsource %q\nset +a\ncd %q\nexec .venv/bin/python worker.py\n' \
    "$WORKER_ENV" "${NEBULA_WIZARD_REPO_ROOT}/worker" > "${RUNTIME_DIR}/worker.sh"
  chmod 700 "${RUNTIME_DIR}/worker.sh"
  printf 'Prepared worker plus receipt, assignment, settlement, event, and reconciliation runner commands in %s.\n' "$RUNTIME_DIR"
}

start_process() {
  local name="$1" path="${RUNTIME_DIR}/$1.sh"
  if [[ "$name" == worker && -f "$PROVIDER_WORKER_PID_FILE" ]]; then
    local provider_pid; provider_pid=$(<"$PROVIDER_WORKER_PID_FILE")
    if [[ "$provider_pid" =~ ^[0-9]+$ ]] && kill -0 "$provider_pid" 2>/dev/null; then
      printf 'Skipping owner runtime Worker because provider Worker pid=%s is already running.\n' "$provider_pid"
      return 0
    fi
  fi
  confirm_action "START-${name^^}" "Start the controlled ${name} process for this supervised demonstration?" || return 0
  nohup "$path" > "${LOG_DIR}/${name}.log" 2>&1 &
  printf '%s\n' "$!" > "${PID_DIR}/${name}.pid"
  chmod 600 "${PID_DIR}/${name}.pid"
  printf 'Started %s with PID %s.\n' "$name" "$!"
}

show_status() {
  local pid_file name pid
  [[ -d "$PID_DIR" ]] || { printf 'No managed demo processes are recorded.\n'; return 0; }
  for pid_file in "$PID_DIR"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    name=$(basename "$pid_file" .pid); pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then printf 'RUNNING %s pid=%s\n' "$name" "$pid"; else printf 'STOPPED %s stale_pid=%s\n' "$name" "$pid"; fi
  done
}

stop_all() {
  local pid_file pid name
  [[ -d "$PID_DIR" ]] || { printf 'No managed demo processes are recorded.\n'; return 0; }
  for pid_file in "$PID_DIR"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    name=$(basename "$pid_file" .pid); pid=$(cat "$pid_file")
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid"
      printf 'Sent TERM to %s pid=%s.\n' "$name" "$pid"
    fi
    rm -f -- "$pid_file"
  done
}

run_wizard() {
  require_interactive_terminal
  init_owner_paths

  stage 1 7 "Validate local Docker/Python/Node prerequisites and clean configuration"
  open_url "https://docs.docker.com/engine/install/"
  check_local
  git -C "$NEBULA_WIZARD_REPO_ROOT" diff --quiet || {
    printf 'Refusing runtime preparation from a dirty tracked worktree.\n' >&2; return 1;
  }

  stage 2 7 "Validate Cloud Run API, Supabase, private R2, RPC, and contract configuration"
  open_url "https://cloud.google.com/run/docs/managing/services"
  open_url "https://developers.cloudflare.com/r2/api/s3/"
  local api_origin database_url rpc_url r2_account r2_bucket r2_access r2_secret contract_address
  api_origin=$(load_value CLOUD_RUN_ORIGIN); database_url=$(load_value DATABASE_URL); rpc_url=$(load_value ARBITRUM_SEPOLIA_RPC)
  r2_account=$(load_value R2_ACCOUNT_ID); r2_bucket=$(load_value R2_BUCKET_NAME); r2_access=$(load_value R2_ACCESS_KEY_ID); r2_secret=$(load_value R2_SECRET_ACCESS_KEY)
  contract_address=$(load_value NEBULA_PAYMENT_CONTRACT)
  require_https_origin CLOUD_RUN_ORIGIN "$api_origin"
  confirm_action "RUN-CONNECTIVITY" "Run reviewed health, Supabase, private R2, RPC, and deployed-contract connectivity checks?"
  run_command "runtime connectivity preflight" timeout 75s "${NEBULA_WIZARD_REPO_ROOT}/backend/.venv/bin/python" "${NEBULA_WIZARD_REPO_ROOT}/scripts/gcp_laptop_runtime_preflight.py" --config-dir "$NEBULA_GCP_CONFIG_DIR"

  stage 3 7 "Validate separate worker, GPU provider, and Verifier identities"
  open_url "https://docs.arbitrum.io/build-decentralized-apps/reference/node-providers"
  local provider_address verifier_address worker_signer_address worker_private_key executor_address executor_private_key node_id api_key
  ask_public provider_address "GPU provider wallet address"
  ask_public verifier_address "Existing Verifier address"
  ask_public worker_signer_address "Worker signer address"
  ask_secret worker_private_key "Worker signer private key"
  ask_public executor_address "Laptop runner/executor address"
  ask_secret executor_private_key "Laptop runner/executor private key"
  ask_public node_id "Registered GPU node ID"
  ask_secret api_key "Worker node API key"
  if [[ "$provider_address" == "$verifier_address" || "$provider_address" == "$worker_signer_address" || "$verifier_address" == "$worker_signer_address" ]]; then
    printf 'Refusing conflated GPU provider, Worker signer, or Verifier identities.\n' >&2; return 1
  fi
  confirm_action "CUSTODY-REVIEWED" "Confirm these identities preserve the existing owner/provider/Worker signer/Verifier custody model."

  stage 4 7 "Prepare worker and each runner command without starting them"
  : > "$BACKEND_ENV"; : > "$WORKER_ENV"; chmod 600 "$BACKEND_ENV" "$WORKER_ENV"
  write_env_assignment "$BACKEND_ENV" DATABASE_URL "$database_url"
  write_env_assignment "$BACKEND_ENV" JWT_SECRET "$(load_value JWT_SECRET)"
  write_env_assignment "$BACKEND_ENV" FRONTEND_URL "$(load_value FRONTEND_URL)"
  write_env_assignment "$BACKEND_ENV" ARBITRUM_SEPOLIA_RPC "$rpc_url"
  write_env_assignment "$BACKEND_ENV" NEBULA_PAYMENT_CONTRACT "$contract_address"
  # Start event ingestion at the deployed contract instead of block zero.
  # The block is public deployment metadata, not a credential.
  write_env_assignment "$BACKEND_ENV" CONTRACT_DEPLOYMENT_BLOCK "312679343"
  write_env_assignment "$BACKEND_ENV" BACKEND_EXECUTOR_ADDRESS "$executor_address"
  write_env_assignment "$BACKEND_ENV" BACKEND_PRIVATE_KEY "$executor_private_key"
  write_env_assignment "$BACKEND_ENV" STORAGE_ADAPTER s3
  write_env_assignment "$BACKEND_ENV" RUNNERS_ENABLED false
  write_env_assignment "$BACKEND_ENV" R2_ACCOUNT_ID "$r2_account"
  write_env_assignment "$BACKEND_ENV" R2_BUCKET_NAME "$r2_bucket"
  write_env_assignment "$BACKEND_ENV" R2_ACCESS_KEY_ID "$r2_access"
  write_env_assignment "$BACKEND_ENV" R2_SECRET_ACCESS_KEY "$r2_secret"
  write_env_assignment "$WORKER_ENV" NODE_ID "$node_id"
  write_env_assignment "$WORKER_ENV" API_KEY "$api_key"
  write_env_assignment "$WORKER_ENV" PRIVATE_KEY "$worker_private_key"
  write_env_assignment "$WORKER_ENV" BACKEND_URL "$api_origin"
  write_env_assignment "$WORKER_ENV" VERIFYING_CONTRACT "$contract_address"
  write_env_assignment "$WORKER_ENV" EXECUTOR_ADAPTER fixture
  prepare_commands
  printf 'Processes are prepared but not started by default.\n'

  stage 5 7 "Require confirmation immediately before every controlled process"
  local process_name
  for process_name in receipts assignment settlement events reconciliation worker; do start_process "$process_name"; done

  stage 6 7 "Safe stop, cleanup, and status procedure"
  show_status
  printf 'Status: %s --status\nStop all managed processes: %s --stop\nLogs: %s\n' "$0" "$0" "$LOG_DIR"

  stage 7 7 "Confirm no continuous runners are hosted on Cloud Run"
  open_url "https://cloud.google.com/run/docs/configuring/min-instances"
  confirm_action "CLOUD-RUN-API-ONLY" "Confirm Cloud Run still has RUNNERS_ENABLED=false, min instances zero, one API container, and no runner process."
  printf 'Controlled processes are laptop-only and must be stopped when the demonstration ends.\n'
}

main() {
  case "${1:-}" in
    --check) [[ $# -eq 1 ]] || return 2; check_local ;;
    --plan) [[ $# -eq 1 ]] || return 2; show_plan ;;
    --run) [[ $# -eq 1 ]] || return 2; run_wizard ;;
    --status) [[ $# -eq 1 ]] || return 2; show_status ;;
    --stop) [[ $# -eq 1 ]] || return 2; stop_all ;;
    --help|-h) show_help ;;
    *) show_help >&2; return 2 ;;
  esac
}

main "$@"
