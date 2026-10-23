#!/usr/bin/env bash
# Shared safety interface for the three Nebula owner-guided deployment wizards.

set -euo pipefail

if [[ "$-" == *x* ]]; then
  printf 'Refusing to run while shell xtrace is enabled. Disable xtrace first.\n' >&2
  exit 2
fi

umask 077

readonly NEBULA_WIZARD_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly NEBULA_GCP_CONFIG_DIR="${NEBULA_GCP_CONFIG_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/nebula-gcp}"
readonly NEBULA_GCP_STATE_DIR="${NEBULA_GCP_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/nebula-gcp}"
readonly NEBULA_GCP_EVIDENCE_DIR="${NEBULA_GCP_STATE_DIR}/evidence"

init_owner_paths() {
  mkdir -p "$NEBULA_GCP_CONFIG_DIR" "$NEBULA_GCP_EVIDENCE_DIR"
  chmod 700 "$NEBULA_GCP_CONFIG_DIR" "$NEBULA_GCP_STATE_DIR" "$NEBULA_GCP_EVIDENCE_DIR"
}

require_interactive_terminal() {
  if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'Refusing --run without an interactive terminal. Use --check or --plan for automation.\n' >&2
    return 2
  fi
}

open_url() {
  local url="$1"
  printf '  Official reference: %s\n' "$url"
  if command -v wslview >/dev/null 2>&1; then
    wslview "$url" >/dev/null 2>&1 || true
  elif command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

stage() {
  printf '\n[%s/%s] %s\n' "$1" "$2" "$3"
}

ask_public() {
  local variable_name="$1" prompt="$2" input=""
  printf '%s: ' "$prompt"
  read -r input
  printf -v "$variable_name" '%s' "$input"
}

ask_secret() {
  local variable_name="$1" prompt="$2" input=""
  printf '%s: ' "$prompt"
  read -rs input
  printf '\n'
  printf -v "$variable_name" '%s' "$input"
}

confirm_action() {
  local phrase="$1" prompt="$2" answer=""
  printf '%s\nType %s to continue: ' "$prompt" "$phrase"
  read -r answer
  [[ "$answer" == "$phrase" ]]
}

reject_placeholder() {
  local label="$1" value="$2"
  if [[ -z "$value" || "$value" == *"__"* || "$value" == *"PLACEHOLDER"* || "$value" == *"CHANGEME"* ]]; then
    printf 'Refusing incomplete or placeholder value for %s.\n' "$label" >&2
    return 1
  fi
}

require_exact() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf 'Refusing %s=%s; required value is %s.\n' "$label" "$actual" "$expected" >&2
    return 1
  fi
}

require_https_origin() {
  local label="$1" value="$2"
  if [[ ! "$value" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ || "$value" == *"@"* ]]; then
    printf 'Refusing invalid credential-free HTTPS origin for %s.\n' "$label" >&2
    return 1
  fi
}

canonicalize_https_origin() {
  local label="$1" value="$2"
  require_https_origin "$label" "$value" || return 1
  python3 -c '
import re
import sys
from urllib.parse import urlsplit

label, value = sys.argv[1:]
parsed = urlsplit(value)
host = parsed.hostname or ""
labels = host.split(".")
valid_label = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
try:
    port = parsed.port
except ValueError:
    port = -1
if not host or len(host) > 253 or any(not valid_label.fullmatch(item) for item in labels) or port == -1:
    print(f"Refusing malformed HTTPS origin for {label}.", file=sys.stderr)
    raise SystemExit(1)
authority = host.lower() if port in (None, 443) else f"{host.lower()}:{port}"
print(f"https://{authority}", end="")
' "$label" "$value"
}

require_digest_image() {
  local value="$1"
  if [[ ! "$value" =~ ^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]]; then
    printf 'Refusing mutable or invalid image reference; an approved sha256 digest is required.\n' >&2
    return 1
  fi
}

save_value() {
  local name="$1" value="$2" path="${NEBULA_GCP_CONFIG_DIR}/$1"
  [[ "$name" =~ ^[A-Z0-9_]+$ ]] || return 1
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || return 1
  printf '%s' "$value" > "$path"
  chmod 600 "$path"
  printf 'Saved %s in protected local configuration.\n' "$name"
}

load_value() {
  local name="$1" path="${NEBULA_GCP_CONFIG_DIR}/$1"
  [[ -f "$path" ]] || return 1
  cat "$path"
}

record_public_evidence() {
  local filename="$1" content="$2" path="${NEBULA_GCP_EVIDENCE_DIR}/$1"
  printf '%s\n' "$content" > "$path"
  chmod 600 "$path"
  printf 'Recorded sanitized evidence at %s.\n' "$path"
}

run_command() {
  local description="$1"
  shift
  printf 'Running reviewed action: %s\n' "$description"
  "$@"
}

check_commands() {
  local failed=0 command_name
  for command_name in "$@"; do
    if command -v "$command_name" >/dev/null 2>&1; then
      printf '  OK  %s\n' "$command_name"
    else
      printf '  ERR %s is unavailable\n' "$command_name" >&2
      failed=1
    fi
  done
  return "$failed"
}
