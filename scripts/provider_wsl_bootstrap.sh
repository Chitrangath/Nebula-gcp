#!/usr/bin/env bash
# Prepare an Ubuntu/WSL provider machine, then hand off to the provider Worker wizard.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
WORKER_DIR="${REPO_ROOT}/worker"

usage() {
  printf 'Usage: %s [--check|--install|--run|--help]\n' "${0##*/}"
  printf '\n  --check   verify host, CUDA, repository, and Worker environment\n'
  printf '  --install install Ubuntu packages, uv, Worker venv, and dependencies\n'
  printf '  --run     install/check, then launch the provider Worker wizard\n'
}

die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

check_wsl() {
  grep -qi microsoft /proc/version || die 'Run this script inside Ubuntu on WSL2.'
  printf '  OK  Ubuntu/WSL2\n'
}

check_gpu() {
  command -v nvidia-smi >/dev/null 2>&1 || die 'nvidia-smi is missing. Install/update the Windows NVIDIA driver with WSL2 CUDA support, then reopen WSL.'
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  "${WORKER_DIR}/.venv/bin/python" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' 2>/dev/null \
    || die 'PyTorch cannot access CUDA. Run --install or check the NVIDIA WSL integration.'
  printf '  OK  NVIDIA and PyTorch CUDA\n'
}

check_repo() {
  [[ -f "${WORKER_DIR}/requirements-cu128.txt" ]] || die 'Run this from a Nebula-gcp checkout.'
  git -C "${REPO_ROOT}" diff --quiet || die 'The repository has tracked changes; use an owner-approved clean commit.'
  printf '  OK  repository and pinned Worker requirements\n'
}

check_environment() {
  command -v git >/dev/null || die 'git is required.'
  command -v curl >/dev/null || die 'curl is required.'
  command -v python3 >/dev/null || die 'python3 is required.'
  check_wsl
  check_repo
  [[ -x "${WORKER_DIR}/.venv/bin/python" ]] || die 'Worker environment is missing; run --install.'
  check_gpu
}

install_environment() {
  check_wsl
  command -v sudo >/dev/null || die 'sudo is required to install Ubuntu packages.'
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git python3 python3-venv python3-pip

  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  command -v uv >/dev/null 2>&1 || die 'uv installation did not become available; reopen WSL and rerun --install.'

  uv venv --python 3.12 "${WORKER_DIR}/.venv"
  uv pip install --python "${WORKER_DIR}/.venv/bin/python" -r "${WORKER_DIR}/requirements-cu128.txt"
  check_gpu
  printf '\nProvider environment is ready. Next: register the node in the public dApp, then run:\n'
  printf '  %s --run\n' "${SCRIPT_DIR}/demo008_provider_worker_wizard.sh"
}

run_provider_wizard() {
  check_environment
  exec "${SCRIPT_DIR}/demo008_provider_worker_wizard.sh" --run
}

main() {
  case "${1:-}" in
    --check) check_environment ;;
    --install) install_environment ;;
    --run) install_environment; run_provider_wizard ;;
    --help|-h) usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

main "$@"
