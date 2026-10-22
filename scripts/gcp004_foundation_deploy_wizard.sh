#!/usr/bin/env bash
# Owner-guided GCP/R2/Cloud Run deployment through direct backend acceptance.

set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/nebula_owner_wizard.sh
source "${SCRIPT_DIR}/lib/nebula_owner_wizard.sh"

readonly SERVICE_TEMPLATE="${NEBULA_WIZARD_REPO_ROOT}/deploy/gcp-demo/cloud-run-service.template.yaml"
readonly REWRITE_TEMPLATE="${NEBULA_WIZARD_REPO_ROOT}/deploy/gcp-demo/vercel-rewrite.template.json"
readonly VALIDATOR="${NEBULA_WIZARD_REPO_ROOT}/scripts/validate_gcp_demo_config.py"
readonly RENDERER="${NEBULA_WIZARD_REPO_ROOT}/scripts/render_gcp_demo_config.py"
readonly DB_PROBE_RENDERER="${NEBULA_WIZARD_REPO_ROOT}/scripts/render_gcp_db_unavailable_probe.py"
readonly MATERIALIZED_SERVICE="${NEBULA_GCP_STATE_DIR}/cloud-run-service.owner.json"
readonly MATERIALIZED_DB_PROBE="${NEBULA_GCP_STATE_DIR}/cloud-run-db-unavailable-probe.owner.json"

repository_is_clean() {
  git -C "$NEBULA_WIZARD_REPO_ROOT" rev-parse --verify HEAD >/dev/null 2>&1 \
    && [[ -z "$(git -C "$NEBULA_WIZARD_REPO_ROOT" status --porcelain --untracked-files=all)" ]]
}

show_plan() {
  printf '%s\n' \
    'GCP-004 owner-guided foundation and direct acceptance:' \
    '  1/13 repository integrity and immutable source checks' \
    '  2/13 project, region, billing, and cost-risk acknowledgement' \
    '  3/13 budget alerts and cost review' \
    '  4/13 required Google API enablement' \
    '  5/13 private Cloudflare R2 bucket creation' \
    '  6/13 bucket-scoped R2 object read/write token creation' \
    '  7/13 runtime service account and least-privilege IAM configuration' \
    '  8/13 numbered Secret Manager secrets' \
    '  9/13 immutable image build, scan, upload, and digest review' \
    '  10/13 API-only Cloud Run deployment with RUNNERS_ENABLED=false and STORAGE_ADAPTER=s3' \
    '  11/13 direct health plus isolated database-unavailable /ready=503 acceptance' \
    '  12/13 Cloud Run and laptop private-object exchange acceptance' \
    '  13/13 explicit stop before Vercel, DNS, or browser routing' \
    '' \
    'The owner confirms every external or billable action immediately before it runs.' \
    'Public R2 access must remain disabled. No Vercel or DNS command exists here.'
}

show_help() {
  printf 'Usage: %s --check | --plan | --bootstrap | --run | --help\n' "${0##*/}"
}

bootstrap_prerequisites() {
  require_interactive_terminal

  stage 1 3 "Ubuntu/WSL host and Google Cloud CLI prerequisite"
  if [[ ! -r /etc/os-release ]]; then
    printf 'Refusing bootstrap because /etc/os-release is unavailable.\n' >&2
    return 1
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    printf 'Refusing automatic package installation on unsupported host ID=%s. Follow the official Google Cloud CLI installation guide.\n' "${ID:-unknown}" >&2
    return 1
  fi
  printf 'Detected Ubuntu %s. This mode installs local tooling only; it creates no cloud resources.\n' "${VERSION_ID:-unknown}"

  if command -v gcloud >/dev/null 2>&1; then
    printf '  OK  %s\n' "$(gcloud version 2>/dev/null | head -n 1)"
  else
    open_url "https://cloud.google.com/sdk/docs/install"
    confirm_action "INSTALL-GCLOUD" "Install Google Cloud CLI from Google's signed apt repository? This uses sudo and changes WSL system packages."
    if [[ -f /usr/share/keyrings/cloud.google.gpg ]]; then
      run_command "repair existing Google Cloud apt signing-key permissions" \
        sudo chmod 0644 /usr/share/keyrings/cloud.google.gpg
    fi
    if [[ -f /etc/apt/sources.list.d/google-cloud-sdk.list ]]; then
      run_command "repair existing Google Cloud repository-definition permissions" \
        sudo chmod 0644 /etc/apt/sources.list.d/google-cloud-sdk.list
    fi
    run_command "refresh Ubuntu package metadata" sudo apt-get update
    run_command "install Google Cloud CLI prerequisites" sudo apt-get install -y ca-certificates gnupg curl

    local key_file dearmored_key repository_file
    key_file=$(mktemp)
    dearmored_key=$(mktemp)
    repository_file=$(mktemp)
    curl --fail --silent --show-error --location \
      "https://packages.cloud.google.com/apt/doc/apt-key.gpg" \
      --output "$key_file"
    gpg --dearmor --yes --output "$dearmored_key" "$key_file"
    run_command "install readable Google Cloud apt signing key" \
      sudo install -o root -g root -m 0644 "$dearmored_key" /usr/share/keyrings/cloud.google.gpg
    printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main' > "$repository_file"
    run_command "install readable Google Cloud apt repository definition" \
      sudo install -o root -g root -m 0644 "$repository_file" /etc/apt/sources.list.d/google-cloud-sdk.list
    rm -f -- "$key_file" "$dearmored_key" "$repository_file"
    run_command "refresh package metadata with Google Cloud repository" sudo apt-get update
    run_command "install Google Cloud CLI" sudo apt-get install -y google-cloud-cli
    command -v gcloud >/dev/null 2>&1 || {
      printf 'Google Cloud CLI installation did not produce a usable gcloud command.\n' >&2
      return 1
    }
    gcloud version
  fi

  stage 2 3 "Owner-controlled Google Cloud authentication"
  open_url "https://cloud.google.com/sdk/docs/authorizing"
  if [[ -n "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" ]]; then
    printf '  OK  an active gcloud account is already configured; no account identifier is printed.\n'
  else
    confirm_action "GCLOUD-LOGIN" "Start console-based Google Cloud user authentication? You will open the printed URL in your browser and paste its authorization code here. No project or cloud resource will be changed."
    run_command "authenticate the owner account without a WSL callback" gcloud auth login --no-launch-browser
  fi

  stage 3 3 "Repeat non-mutating GCP-004 preflight"
  check_local
  printf '\nBootstrap complete. Review --plan next; do not use --run until the source tree is reviewed and clean.\n'
}

check_local() {
  local failed=0
  printf 'GCP-004 local-only prerequisite check\n'
  check_commands bash python3 git || failed=1
  for optional in gcloud docker curl; do
    command -v "$optional" >/dev/null 2>&1 \
      && printf '  OK  %s is available\n' "$optional" \
      || printf '  WARN %s is required when the owner later executes --run\n' "$optional"
  done
  for path in "$SERVICE_TEMPLATE" "$REWRITE_TEMPLATE" "$VALIDATOR" "$RENDERER" "$DB_PROBE_RENDERER"; do
    [[ -f "$path" ]] && printf '  OK  %s\n' "${path#"${NEBULA_WIZARD_REPO_ROOT}/"}" || { printf '  ERR missing %s\n' "$path" >&2; failed=1; }
  done
  repository_is_clean \
    && printf '  OK  worktree is clean\n' \
    || printf '  WARN worktree is dirty or unavailable; --run will refuse until changes are reviewed and committed\n'
  python3 "$VALIDATOR" --template --service "$SERVICE_TEMPLATE" --rewrite "$REWRITE_TEMPLATE" || failed=1
  (( failed == 0 ))
}

create_secret_version() {
  local project="$1" name="$2" value="$3"
  if gcloud secrets describe "$name" --project "$project" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --project "$project" --data-file=- >/dev/null
  else
    printf '%s' "$value" | gcloud secrets create "$name" --project "$project" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

run_wizard() {
  require_interactive_terminal
  init_owner_paths

  stage 1 13 "Local prerequisite, repository-integrity, and source/digest checks"
  open_url "https://cloud.google.com/run/docs/deploying-source-code"
  check_local
  repository_is_clean || {
    printf 'Refusing deployment from a dirty or unavailable worktree.\n' >&2; return 1;
  }
  local source_commit
  source_commit=$(git -C "$NEBULA_WIZARD_REPO_ROOT" rev-parse HEAD)
  reject_placeholder SOURCE_COMMIT "$source_commit"
  confirm_action "SOURCE-REVIEWED" "Confirm this clean commit is the reviewed deployment source."
  save_value SOURCE_COMMIT "$source_commit"

  stage 2 13 "GCP project, approved region, billing, and explicit cost-risk acknowledgement"
  open_url "https://console.cloud.google.com/cloud-resource-manager"
  open_url "https://cloud.google.com/run/pricing"
  open_url "https://docs.arbitrum.io/build-decentralized-apps/reference/useful-addresses"
  local project region service_name frontend_origin contract_address deployment_block owner_address verifier_address
  ask_public project "Exact owner-approved GCP project ID"
  ask_public region "Exact owner-approved Cloud Run region"
  ask_public service_name "Cloud Run service name"
  ask_public frontend_origin "Exact Vercel frontend production HTTPS origin"
  ask_public contract_address "Existing NebulaPayment deployed contract address"
  ask_public deployment_block "Existing contract deployment block"
  ask_public owner_address "Existing contract owner address"
  ask_public verifier_address "Existing contract Verifier address"
  reject_placeholder GCP_PROJECT_ID "$project"
  reject_placeholder GCP_REGION "$region"
  reject_placeholder CLOUD_RUN_SERVICE "$service_name"
  require_https_origin FRONTEND_URL "$frontend_origin"
  reject_placeholder NEBULA_PAYMENT_CONTRACT "$contract_address"; reject_placeholder CONTRACT_DEPLOYMENT_BLOCK "$deployment_block"
  reject_placeholder CONTRACT_OWNER_ADDRESS "$owner_address"; reject_placeholder CONTRACT_VERIFIER_ADDRESS "$verifier_address"
  confirm_action "I-ACCEPT-COST-RISK" "Billing, logs, builds, registry, secrets, egress, R2, and Supabase can incur charges; budgets are not hard caps."
  save_value GCP_PROJECT_ID "$project"; save_value GCP_REGION "$region"; save_value CLOUD_RUN_SERVICE "$service_name"; save_value FRONTEND_URL "$frontend_origin"
  save_value NEBULA_PAYMENT_CONTRACT "$contract_address"; save_value CONTRACT_DEPLOYMENT_BLOCK "$deployment_block"; save_value CONTRACT_OWNER_ADDRESS "$owner_address"; save_value CONTRACT_VERIFIER_ADDRESS "$verifier_address"

  stage 3 13 "Budget alerts and cost-review confirmation"
  open_url "https://console.cloud.google.com/billing/budgets"
  open_url "https://cloud.google.com/billing/docs/how-to/budgets"
  confirm_action "BUDGET-REVIEWED" "Create and review the owner-approved alert thresholds and recipients before continuing."

  stage 4 13 "Required Google API enablement"
  open_url "https://console.cloud.google.com/apis/library"
  open_url "https://cloud.google.com/service-usage/docs/enable-disable"
  confirm_action "ENABLE-APIS" "Enable run.googleapis.com, artifactregistry.googleapis.com, and secretmanager.googleapis.com in the approved project?"
  run_command "enable required Google APIs" gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project "$project"

  stage 5 13 "Private Cloudflare R2 bucket creation"
  open_url "https://dash.cloudflare.com/?to=/:account/r2/overview"
  open_url "https://developers.cloudflare.com/r2/buckets/create-buckets/"
  local r2_account r2_bucket storage_prefix
  ask_public r2_account "R2 account ID"
  ask_public r2_bucket "Private R2 bucket name"
  ask_public storage_prefix "Dedicated object prefix (one segment)"
  reject_placeholder R2_ACCOUNT_ID "$r2_account"; reject_placeholder R2_BUCKET_NAME "$r2_bucket"; reject_placeholder OBJECT_STORAGE_PREFIX "$storage_prefix"
  confirm_action "R2-PRIVATE" "Confirm the bucket exists and public R2.dev/custom-domain access is disabled; public R2 access must remain disabled."
  save_value R2_ACCOUNT_ID "$r2_account"; save_value R2_BUCKET_NAME "$r2_bucket"; save_value OBJECT_STORAGE_PREFIX "$storage_prefix"

  stage 6 13 "Bucket-scoped R2 object read/write token creation"
  open_url "https://developers.cloudflare.com/r2/api/tokens/"
  local r2_access r2_secret
  ask_secret r2_access "R2 access key ID for the bucket-scoped Object Read & Write token"
  ask_secret r2_secret "R2 secret access key"
  reject_placeholder R2_ACCESS_KEY_ID "$r2_access"; reject_placeholder R2_SECRET_ACCESS_KEY "$r2_secret"
  confirm_action "TOKEN-SCOPED" "Confirm this token is restricted to only the private demo bucket and has no bucket-management permission."
  save_value R2_ACCESS_KEY_ID "$r2_access"; save_value R2_SECRET_ACCESS_KEY "$r2_secret"

  stage 7 13 "GCP runtime service account and least-privilege IAM configuration"
  open_url "https://console.cloud.google.com/iam-admin/serviceaccounts"
  open_url "https://cloud.google.com/run/docs/securing/service-identity"
  local runtime_sa
  ask_public runtime_sa "Dedicated runtime service-account email"
  reject_placeholder RUNTIME_SERVICE_ACCOUNT "$runtime_sa"
  confirm_action "CREATE-RUNTIME-IDENTITY" "Create/review the dedicated runtime identity with no Editor, Owner, build, deploy, registry-write, or signing-key role?"
  if ! gcloud iam service-accounts describe "$runtime_sa" --project "$project" >/dev/null 2>&1; then
    run_command "create dedicated runtime identity" gcloud iam service-accounts create "${runtime_sa%@*}" --project "$project" --display-name "Nebula demo API runtime"
  fi
  confirm_action "DEPLOYER-IAM-REVIEWED" "Confirm the owner/deployer has only the reviewed Cloud Run, Artifact Registry Reader, and Service Account User permissions required for this named deployment."
  save_value RUNTIME_SERVICE_ACCOUNT "$runtime_sa"

  stage 8 13 "Numbered Secret Manager secret creation"
  open_url "https://console.cloud.google.com/security/secret-manager"
  open_url "https://cloud.google.com/run/docs/configuring/services/secrets"
  local database_url jwt_secret rpc_url
  ask_secret database_url "Supabase PostgreSQL DATABASE_URL"
  ask_secret jwt_secret "JWT signing secret"
  ask_secret rpc_url "Arbitrum Sepolia RPC URL"
  reject_placeholder DATABASE_URL "$database_url"; reject_placeholder JWT_SECRET "$jwt_secret"; reject_placeholder ARBITRUM_SEPOLIA_RPC "$rpc_url"
  confirm_action "CREATE-SECRETS" "Create or add numbered versions for the five reviewed runtime secrets without printing their values?"
  create_secret_version "$project" nebula-demo-database-url "$database_url"
  create_secret_version "$project" nebula-demo-jwt-secret "$jwt_secret"
  create_secret_version "$project" nebula-demo-rpc "$rpc_url"
  create_secret_version "$project" nebula-demo-r2-access-key "$r2_access"
  create_secret_version "$project" nebula-demo-r2-secret-key "$r2_secret"
  confirm_action "GRANT-SECRET-ACCESS" "Grant the runtime identity Secret Accessor on only these five secrets?"
  local secret_name
  for secret_name in nebula-demo-database-url nebula-demo-jwt-secret nebula-demo-rpc nebula-demo-r2-access-key nebula-demo-r2-secret-key; do
    run_command "grant exact-secret runtime access" gcloud secrets add-iam-policy-binding "$secret_name" --project "$project" --member "serviceAccount:${runtime_sa}" --role roles/secretmanager.secretAccessor
  done
  local database_version jwt_version rpc_version r2_access_version r2_secret_version
  database_version=$(gcloud secrets versions list nebula-demo-database-url --project "$project" --filter='state:ENABLED' --sort-by='~name' --limit=1 --format='value(name)')
  jwt_version=$(gcloud secrets versions list nebula-demo-jwt-secret --project "$project" --filter='state:ENABLED' --sort-by='~name' --limit=1 --format='value(name)')
  rpc_version=$(gcloud secrets versions list nebula-demo-rpc --project "$project" --filter='state:ENABLED' --sort-by='~name' --limit=1 --format='value(name)')
  r2_access_version=$(gcloud secrets versions list nebula-demo-r2-access-key --project "$project" --filter='state:ENABLED' --sort-by='~name' --limit=1 --format='value(name)')
  r2_secret_version=$(gcloud secrets versions list nebula-demo-r2-secret-key --project "$project" --filter='state:ENABLED' --sort-by='~name' --limit=1 --format='value(name)')
  database_version=${database_version##*/}; jwt_version=${jwt_version##*/}; rpc_version=${rpc_version##*/}
  r2_access_version=${r2_access_version##*/}; r2_secret_version=${r2_secret_version##*/}
  save_value DATABASE_SECRET_VERSION "$database_version"; save_value JWT_SECRET_VERSION "$jwt_version"; save_value RPC_SECRET_VERSION "$rpc_version"
  save_value R2_ACCESS_KEY_SECRET_VERSION "$r2_access_version"; save_value R2_SECRET_KEY_SECRET_VERSION "$r2_secret_version"
  save_value DATABASE_URL "$database_url"; save_value JWT_SECRET "$jwt_secret"; save_value ARBITRUM_SEPOLIA_RPC "$rpc_url"

  stage 9 13 "Immutable image build, scan, upload, and digest review"
  open_url "https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling"
  local image_digest
  if ! gcloud artifacts repositories describe nebula --location "$region" --project "$project" >/dev/null 2>&1; then
    confirm_action "CREATE-REGISTRY" "Create the regional nebula Docker repository (a billable external resource)?"
    run_command "create regional Artifact Registry repository" gcloud artifacts repositories create nebula --repository-format=docker --location "$region" --project "$project" --description "Nebula GCP demo images"
  fi
  confirm_action "BUILD-IMAGE" "Build the reviewed backend Dockerfile locally?"
  run_command "build local backend image" docker build -t "${region}-docker.pkg.dev/${project}/nebula/api:gcp004-candidate" "${NEBULA_WIZARD_REPO_ROOT}/backend"
  if command -v trivy >/dev/null 2>&1; then run_command "scan candidate image" trivy image "${region}-docker.pkg.dev/${project}/nebula/api:gcp004-candidate"; fi
  confirm_action "UPLOAD-IMAGE" "Authenticate Docker to the approved regional registry and upload this reviewed candidate?"
  run_command "configure regional Docker authentication" gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
  run_command "upload reviewed candidate image" docker push "${region}-docker.pkg.dev/${project}/nebula/api:gcp004-candidate"
  ask_public image_digest "Paste the registry image reference pinned by @sha256:"
  require_digest_image "$image_digest"
  confirm_action "DIGEST-REVIEWED" "Confirm the digest matches the uploaded, tested image."
  save_value IMAGE_DIGEST "$image_digest"

  stage 10 13 "API-only Cloud Run deployment with runners disabled"
  open_url "https://cloud.google.com/run/docs/deploying"
  local runners_enabled=false storage_adapter=s3
  require_exact RUNNERS_ENABLED false "$runners_enabled"
  require_exact STORAGE_ADAPTER s3 "$storage_adapter"
  python3 "$RENDERER" --config-dir "$NEBULA_GCP_CONFIG_DIR" --output "$MATERIALIZED_SERVICE"
  python3 "$VALIDATOR" --service "$MATERIALIZED_SERVICE" --service-only
  confirm_action "DEPLOY-API-ONLY" "Deploy the validated digest-pinned API-only service with min instances zero and no runners?"
  run_command "deploy validated Cloud Run service" gcloud run services replace "$MATERIALIZED_SERVICE" --project "$project" --region "$region"
  confirm_action "MAKE-PUBLIC" "Allow unauthenticated invocation of the API service while preserving application authentication?"
  run_command "grant public invocation only" gcloud run services add-iam-policy-binding "$service_name" --project "$project" --region "$region" --member=allUsers --role=roles/run.invoker

  stage 11 13 "Direct public /live and database-backed /ready acceptance"
  open_url "https://cloud.google.com/run/docs/monitoring/healthchecks"
  local cloud_run_origin
  ask_public cloud_run_origin "Observed Cloud Run service HTTPS origin"
  require_https_origin CLOUD_RUN_ORIGIN "$cloud_run_origin"
  confirm_action "RUN-DIRECT-HEALTH" "Run direct public liveness and database-backed readiness checks now?"
  run_command "check direct liveness" curl --fail --silent --show-error "${cloud_run_origin%/}/live"
  run_command "check database-backed readiness" curl --fail --silent --show-error "${cloud_run_origin%/}/ready"

  local probe_service probe_origin probe_live_status probe_ready_status probe_failed=0
  probe_service="${service_name}-db-probe"
  if (( ${#probe_service} > 63 )); then
    printf 'Refusing database probe because the derived service name exceeds 63 characters.\n' >&2
    return 1
  fi
  python3 "$DB_PROBE_RENDERER" \
    --service "$MATERIALIZED_SERVICE" \
    --output "$MATERIALIZED_DB_PROBE" \
    --probe-service "$probe_service"
  confirm_action "DATABASE-FAILURE-PROBE" "Create an isolated, min-zero, max-one temporary Cloud Run service using the same image and an intentionally unreachable dummy database URL? It receives no production traffic and may incur a small charge."
  run_command "deploy isolated database-unavailable probe" \
    gcloud run services replace "$MATERIALIZED_DB_PROBE" --project "$project" --region "$region"
  confirm_action "MAKE-DATABASE-PROBE-PUBLIC" "Temporarily allow unauthenticated invocation of the isolated probe so its /live and /ready responses can be tested?"
  run_command "grant temporary public invocation to database probe" \
    gcloud run services add-iam-policy-binding "$probe_service" --project "$project" --region "$region" --member=allUsers --role=roles/run.invoker
  probe_origin=$(gcloud run services describe "$probe_service" --project "$project" --region "$region" --format='value(status.url)')
  require_https_origin DATABASE_PROBE_ORIGIN "$probe_origin"
  probe_live_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 15 "${probe_origin%/}/live") || probe_live_status="curl-error"
  probe_ready_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 15 "${probe_origin%/}/ready") || probe_ready_status="curl-error"
  [[ "$probe_live_status" == "200" ]] || { printf 'Database probe /live returned %s; expected 200.\n' "$probe_live_status" >&2; probe_failed=1; }
  [[ "$probe_ready_status" == "503" ]] || { printf 'Database probe /ready returned %s; expected 503.\n' "$probe_ready_status" >&2; probe_failed=1; }
  confirm_action "DELETE-DATABASE-PROBE" "Delete the isolated database-unavailable probe service now? Refusing leaves a billable resource, so do not continue without deletion."
  run_command "delete isolated database-unavailable probe" \
    gcloud run services delete "$probe_service" --project "$project" --region "$region" --quiet
  (( probe_failed == 0 )) || return 1
  printf 'Database-unavailable readiness gate passed: /live=200 and /ready=503.\n'
  save_value CLOUD_RUN_ORIGIN "$cloud_run_origin"

  stage 12 13 "Cloud Run and laptop private-object exchange acceptance"
  open_url "https://developers.cloudflare.com/r2/api/s3/"
  printf '%s\n' \
    'Follow the GCP-004 runbook using one non-production fixture job through the existing authenticated worker interface.' \
    'Prove Cloud Run stored the accepted input/model, the laptop Worker retrieved them, the result upload reached Cloud Run storage, and the authorized result download hash matches.' \
    'Record hashes only; never record bytes, credentials, cookies, tokens, or capability URLs.'
  local input_hash result_hash
  ask_public input_hash "Sanitized accepted-input SHA-256 evidence"
  ask_public result_hash "Sanitized result SHA-256 evidence"
  [[ "$input_hash" =~ ^[0-9a-f]{64}$ && "$result_hash" =~ ^[0-9a-f]{64}$ ]] || { printf 'Refusing invalid storage acceptance hashes.\n' >&2; return 1; }
  confirm_action "STORAGE-EXCHANGE-ACCEPTED" "Confirm the existing private authenticated flow passed in both directions with no public object access."
  record_public_evidence GCP004_DIRECT_ACCEPTANCE.env "STATUS=accepted
SOURCE_COMMIT=${source_commit}
CLOUD_RUN_ORIGIN=${cloud_run_origin}
IMAGE_DIGEST=${image_digest}
RUNNERS_ENABLED=false
STORAGE_ADAPTER=s3
PUBLIC_R2=false
INPUT_SHA256=${input_hash}
RESULT_SHA256=${result_hash}"

  stage 13 13 "Explicit stop before Vercel, DNS, or browser routing"
  printf 'STOP: GCP-004 is complete only through direct backend acceptance.\n'
  printf 'Do not modify Vercel, DNS, frontend routing, or browser authentication here.\n'
  printf 'Rollback: stop laptop processes, route Cloud Run to the prior revision or zero traffic, and preserve sanitized evidence.\n'
}

main() {
  case "${1:-}" in
    --check) [[ $# -eq 1 ]] || return 2; check_local ;;
    --plan) [[ $# -eq 1 ]] || return 2; show_plan ;;
    --bootstrap) [[ $# -eq 1 ]] || return 2; bootstrap_prerequisites ;;
    --run) [[ $# -eq 1 ]] || return 2; run_wizard ;;
    --help|-h) show_help ;;
    *) show_help >&2; return 2 ;;
  esac
}

main "$@"
