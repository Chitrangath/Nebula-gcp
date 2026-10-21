"""Behavior tests for the local, API-only GCP demo hosting adapter."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_TEMPLATE = ROOT / "deploy/gcp-demo/cloud-run-service.template.yaml"
REWRITE_TEMPLATE = ROOT / "deploy/gcp-demo/vercel-rewrite.template.json"
VALIDATOR = ROOT / "scripts/validate_gcp_demo_config.py"
WIZARD = ROOT / "scripts/gcp_demo_owner_wizard.sh"
PRD = ROOT / "docs/NEBULA_PRD_v3.1.md"
THREAT_MODEL = ROOT / "docs/security/GCP_DEMO_DEPLOYMENT_THREAT_MODEL.md"
RUNBOOK = ROOT / "docs/runbooks/GCP_DEMO_HOST.md"
FIXED_BASE = "cbc1a25bd912a7e0c421e741cc068563980e0aa9"
SAFE_REPLACEMENTS = {
    "__OWNER_APPROVED_SERVICE_NAME__": "nebula-gcp-demo-api",
    "__OWNER_APPROVED_RUNTIME_SERVICE_ACCOUNT__": "nebula-api@example-project.iam.gserviceaccount.com",
    "__OWNER_APPROVED_IMAGE_DIGEST__": "us-central1-docker.pkg.dev/example-project/nebula/api@sha256:"
    + "a" * 64,
    "__REAL_VERCEL_HTTPS_ORIGIN_REQUIRED__": "https://frontend.example.com",
    "__OWNER_APPROVED_DATABASE_URL_SECRET__": "nebula-demo-database-url",
    "__OWNER_APPROVED_DATABASE_URL_SECRET_VERSION__": "1",
    "__OWNER_APPROVED_JWT_SECRET__": "nebula-demo-jwt-secret",
    "__OWNER_APPROVED_JWT_SECRET_VERSION__": "1",
    "__OWNER_APPROVED_RPC_SECRET__": "nebula-demo-rpc",
    "__OWNER_APPROVED_RPC_SECRET_VERSION__": "1",
    "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET__": "nebula-demo-r2-access-key",
    "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET_VERSION__": "1",
    "__OWNER_APPROVED_R2_SECRET_KEY_SECRET__": "nebula-demo-r2-secret-key",
    "__OWNER_APPROVED_R2_SECRET_KEY_SECRET_VERSION__": "1",
    "__OWNER_APPROVED_CONTRACT_ADDRESS__": "0x1111111111111111111111111111111111111111",
    "__OWNER_APPROVED_CONTRACT_DEPLOYMENT_BLOCK__": "123456789",
    "__OWNER_APPROVED_CONTRACT_OWNER_ADDRESS__": "0x2222222222222222222222222222222222222222",
    "__OWNER_APPROVED_CONTRACT_VERIFIER_ADDRESS__": "0x3333333333333333333333333333333333333333",
    "__OWNER_APPROVED_R2_ACCOUNT_ID__": "a" * 32,
    "__OWNER_APPROVED_R2_BUCKET_NAME__": "nebula-demo-private",
    "__OWNER_APPROVED_STORAGE_PREFIX__": "demo",
    "__OWNER_APPROVED_CLOUD_RUN_HTTPS_ORIGIN__": "https://nebula-api-example.us-central1.run.app",
}


def materialized_templates() -> tuple[str, str]:
    service_text = SERVICE_TEMPLATE.read_text(encoding="utf-8")
    rewrite_text = REWRITE_TEMPLATE.read_text(encoding="utf-8")
    for placeholder, value in SAFE_REPLACEMENTS.items():
        service_text = service_text.replace(placeholder, value)
        rewrite_text = rewrite_text.replace(placeholder, value)
    return service_text, rewrite_text


class GcpDemoServiceContractTest(unittest.TestCase):
    def test_service_is_request_based_api_only_and_scales_to_zero(self) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        template = service["spec"]["template"]
        annotations = template["metadata"]["annotations"]
        containers = template["spec"]["containers"]

        self.assertEqual(service["kind"], "Service")
        self.assertEqual(annotations["autoscaling.knative.dev/minScale"], "0")
        self.assertEqual(annotations["autoscaling.knative.dev/maxScale"], "2")
        self.assertEqual(annotations["run.googleapis.com/cpu-throttling"], "true")
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["name"], "api")
        environment = {item["name"]: item.get("value") for item in containers[0]["env"]}
        self.assertEqual(environment["RUNNERS_ENABLED"], "false")

    def test_validator_rejects_any_gcp_runner_configuration(self) -> None:
        service_text, rewrite_text = materialized_templates()
        service = json.loads(service_text)
        container = service["spec"]["template"]["spec"]["containers"][0]
        container["env"].append({"name": "RECEIPT_RUNNER_ENABLED", "value": "true"})

        with tempfile.TemporaryDirectory() as directory:
            service_path = Path(directory) / "service.json"
            rewrite_path = Path(directory) / "rewrite.json"
            service_path.write_text(json.dumps(service), encoding="utf-8")
            rewrite_path.write_text(rewrite_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--service",
                    str(service_path),
                    "--rewrite",
                    str(rewrite_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("runner configuration is forbidden", result.stderr)

    def test_gcp_profile_has_no_runner_process_or_runner_command(self) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        containers = service["spec"]["template"]["spec"]["containers"]
        serialized = json.dumps(service).lower()

        self.assertEqual([container["name"] for container in containers], ["api"])
        self.assertIn("uvicorn app.main:app", " ".join(containers[0]["args"]))
        for runner in (
            "receipt_runner",
            "assignment_runner",
            "settlement_runner",
            "event_runner",
            "reconciliation_runner",
        ):
            self.assertNotIn(runner, serialized)

    def test_api_consumes_cloud_run_port_and_exposes_only_readiness_probe(self) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        container = service["spec"]["template"]["spec"]["containers"][0]

        self.assertIn(
            "${PORT:?Cloud Run PORT is required}", " ".join(container["args"])
        )
        self.assertEqual(container["ports"], [{"name": "http1", "containerPort": 8080}])
        self.assertEqual(
            container["startupProbe"]["httpGet"], {"path": "/ready", "port": 8080}
        )
        self.assertNotIn("livenessProbe", container)

    def test_sensitive_settings_are_secret_references_not_values(self) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        container = service["spec"]["template"]["spec"]["containers"][0]
        environment = {item["name"]: item for item in container["env"]}

        for name in (
            "DATABASE_URL",
            "JWT_SECRET",
            "ARBITRUM_SEPOLIA_RPC",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        ):
            self.assertNotIn("value", environment[name])
            self.assertIn("secretKeyRef", environment[name]["valueFrom"])

    def test_deployed_profile_requires_complete_runtime_and_durable_storage(
        self,
    ) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        environment = {
            item["name"]: item
            for item in service["spec"]["template"]["spec"]["containers"][0]["env"]
        }

        self.assertEqual(environment["STORAGE_ADAPTER"]["value"], "s3")
        self.assertNotIn("LOCAL_STORAGE_PATH", environment)
        for name in (
            "DATABASE_URL",
            "FRONTEND_URL",
            "JWT_SECRET",
            "JWT_EXPIRY_HOURS",
            "JWT_REFRESH_EXPIRY_HOURS",
            "ARBITRUM_SEPOLIA_RPC",
            "CHAIN_ID",
            "USDC_SEPOLIA_ADDRESS",
            "NEBULA_PAYMENT_CONTRACT",
            "CONTRACT_DEPLOYMENT_BLOCK",
            "CONTRACT_OWNER_ADDRESS",
            "CONTRACT_VERIFIER_ADDRESS",
            "R2_ACCOUNT_ID",
            "R2_BUCKET_NAME",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "OBJECT_STORAGE_REGION",
            "OBJECT_STORAGE_PREFIX",
            "OBJECT_STORAGE_CAPABILITY_TTL_SECONDS",
            "RUNNERS_ENABLED",
        ):
            self.assertIn(name, environment)

    def test_validator_rejects_file_storage_for_deployed_profile(self) -> None:
        service_text, rewrite_text = materialized_templates()
        service = json.loads(service_text)
        environment = service["spec"]["template"]["spec"]["containers"][0]["env"]
        next(item for item in environment if item["name"] == "STORAGE_ADAPTER")[
            "value"
        ] = "file"

        with tempfile.TemporaryDirectory() as directory:
            service_path = Path(directory) / "service.json"
            rewrite_path = Path(directory) / "rewrite.json"
            service_path.write_text(json.dumps(service), encoding="utf-8")
            rewrite_path.write_text(rewrite_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--service",
                    str(service_path),
                    "--rewrite",
                    str(rewrite_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("STORAGE_ADAPTER must equal s3", result.stderr)

    def test_vercel_rewrite_preserves_the_same_origin_browser_interface(self) -> None:
        rewrite = json.loads(REWRITE_TEMPLATE.read_text(encoding="utf-8"))

        self.assertEqual(
            rewrite["rewrites"][0],
            {
                "source": "/api/v1/:path*",
                "destination": "__OWNER_APPROVED_CLOUD_RUN_HTTPS_ORIGIN__/v1/:path*",
            },
        )
        self.assertEqual(rewrite["rewrites"][1]["destination"], "/index.html")
        api_headers = {
            item["key"]: item["value"] for item in rewrite["headers"][0]["headers"]
        }
        self.assertEqual(api_headers["x-vercel-enable-rewrite-caching"], "0")

    def test_validator_refuses_to_treat_placeholders_as_deployable(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--service",
                str(SERVICE_TEMPLATE),
                "--rewrite",
                str(REWRITE_TEMPLATE),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("owner-approved values are still placeholders", result.stderr)

    def test_validator_reports_malformed_shapes_without_a_traceback(self) -> None:
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        service["metadata"] = None

        with tempfile.TemporaryDirectory() as directory:
            service_path = Path(directory) / "malformed-service.json"
            service_path.write_text(json.dumps(service), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--template",
                    "--service",
                    str(service_path),
                    "--rewrite",
                    str(REWRITE_TEMPLATE),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("configuration shape is invalid", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_validator_accepts_only_owner_materialized_safe_values(self) -> None:
        service_text, rewrite_text = materialized_templates()

        with tempfile.TemporaryDirectory() as directory:
            service_path = Path(directory) / "service.json"
            rewrite_path = Path(directory) / "rewrite.json"
            service_path.write_text(service_text, encoding="utf-8")
            rewrite_path.write_text(rewrite_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--service",
                    str(service_path),
                    "--rewrite",
                    str(rewrite_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validator_reports_malformed_origins_without_a_traceback(self) -> None:
        service_text, rewrite_text = materialized_templates()
        service_text = service_text.replace(
            "https://frontend.example.com", "https://[bad"
        )

        with tempfile.TemporaryDirectory() as directory:
            service_path = Path(directory) / "service.json"
            rewrite_path = Path(directory) / "rewrite.json"
            service_path.write_text(service_text, encoding="utf-8")
            rewrite_path.write_text(rewrite_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--service",
                    str(service_path),
                    "--rewrite",
                    str(rewrite_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FRONTEND_URL is not a valid URL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_tracked_templates_have_no_secret_values_or_real_cloud_identifiers(
        self,
    ) -> None:
        tracked_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SERVICE_TEMPLATE, REWRITE_TEMPLATE)
        )
        forbidden_patterns = (
            r"-----BEGIN .*PRIVATE KEY-----",
            r"(?i)postgres(?:ql)?://[^\s:@]+:[^\s@]+@",
            r"(?i)https://[^\s/@]+:[^\s/@]+@",
            r"AIza[0-9A-Za-z_-]{35}",
            r"AKIA[0-9A-Z]{16}",
            r"(?i)[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com",
            r"https://[a-z0-9-]+(?:-[a-z0-9-]+)*\.[a-z0-9-]+\.run\.app",
        )
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, tracked_text), pattern)

        self.assertNotIn("deploy/oci", tracked_text)
        self.assertNotIn("be002_production_auth_wizard", tracked_text)

    def test_frontend_remains_provider_neutral_and_same_origin(self) -> None:
        constants = (ROOT / "frontend/src/utils/constants.ts").read_text(
            encoding="utf-8"
        )
        frontend_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "frontend/src").rglob("*.ts*")
        )

        self.assertIn("API_BASE_URL = '/api/v1'", constants)
        self.assertNotIn("run.app", frontend_sources)

    def test_oci_files_are_unchanged_absent_and_not_adapter_dependencies(self) -> None:
        changed = subprocess.run(
            [
                "git",
                "--git-dir=.git-local",
                "--work-tree=.",
                "diff",
                "--name-only",
                FIXED_BASE,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

        self.assertFalse(any(path.startswith("deploy/oci/") for path in changed))
        self.assertNotIn("scripts/be002_production_auth_wizard.sh", changed)
        self.assertFalse((ROOT / "deploy/oci").exists())
        self.assertFalse((ROOT / "scripts/be002_production_auth_wizard.sh").exists())

        executable_contract = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SERVICE_TEMPLATE, REWRITE_TEMPLATE, VALIDATOR, WIZARD)
        )
        self.assertNotIn("deploy/oci", executable_contract)
        self.assertNotIn("be002_production_auth_wizard", executable_contract)

    def test_service_overrides_backend_default_port_with_cloud_run_port(self) -> None:
        dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
        service = json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))
        container = service["spec"]["template"]["spec"]["containers"][0]

        self.assertIn("app.main:app", dockerfile)
        self.assertEqual(container["command"], ["/bin/sh"])
        self.assertIn("app.main:app", " ".join(container["args"]))
        self.assertIn("--port", " ".join(container["args"]))
        self.assertIn(
            "${PORT:?Cloud Run PORT is required}", " ".join(container["args"])
        )


class GcpDemoWizardContractTest(unittest.TestCase):
    def run_wizard(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(WIZARD), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_default_execution_refuses_all_external_actions(self) -> None:
        result = self.run_wizard()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("GCP-003 is local planning only", result.stderr)
        self.assertIn("--check", result.stderr)
        self.assertIn("--plan", result.stderr)

    def test_plan_remains_non_mutating(self) -> None:
        result = self.run_wizard("--plan")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No action was performed", result.stdout)

    def test_gcp003_plan_exposes_every_owner_gate_in_order(self) -> None:
        result = self.run_wizard("--plan")
        stages = (
            "project, region, and billing approval",
            "budget alerts and cost review",
            "required API enablement",
            "private durable-storage bucket provisioning",
            "least-privilege IAM and bucket-scoped object token",
            "secret creation with pinned versions",
            "immutable image review",
            "Cloud Run deployment",
            "public /live and database-backed /ready",
            "cross-runtime private storage acceptance",
            "Vercel same-origin rewrite cutover",
            "real browser authentication smoke",
            "rollback and OCI switch-back",
        )

        positions = [result.stdout.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("GCP-003", result.stdout)
        self.assertIn("No action was performed", result.stdout)

    def test_wizard_contains_no_external_mutation_commands(self) -> None:
        wizard = WIZARD.read_text(encoding="utf-8")
        forbidden_commands = (
            r"^\s*gcloud\s",
            r"^\s*vercel\s",
            r"^\s*docker\s+(?:build|push)",
            r"^\s*curl\s",
            r"^\s*gh\s+(?:secret|variable)",
        )
        for pattern in forbidden_commands:
            self.assertIsNone(re.search(pattern, wizard, flags=re.MULTILINE), pattern)


class Gcp002DocumentationContractTest(unittest.TestCase):
    def test_prd_deployment_sections_define_the_approved_demo_topology(self) -> None:
        prd = PRD.read_text(encoding="utf-8")

        for statement in (
            "Google Cloud Run deployed demo API host",
            "owner laptop runs the worker and five controlled runners",
            "no continuous hosted runners",
            "no real GPU proof",
            "no production SLA",
            "no production-readiness claim",
            "OCI remains canonical in the original repository",
        ):
            self.assertIn(statement, prd)

    def test_threat_model_covers_required_gcp002_risks_and_controls(self) -> None:
        threat_model = THREAT_MODEL.read_text(encoding="utf-8")

        for topic in (
            "Public Cloud Run ingress",
            "Vercel rewrite and hostname trust",
            "Least-privilege service identity",
            "Secret Manager delivery and rotation",
            "Public traffic abuse",
            "Logs, egress, build, and registry cost exposure",
            "Rollback",
            "OCI switch-back",
        ):
            self.assertIn(topic, threat_model)

        for runtime_setting in (
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "ARBITRUM_SEPOLIA_RPC",
            "NEBULA_PAYMENT_CONTRACT",
            "BACKEND_PRIVATE_KEY",
        ):
            self.assertIn(runtime_setting, threat_model)

    def test_local_storage_and_runtime_gap_is_closed_without_cloud_claim(self) -> None:
        threat_model = THREAT_MODEL.read_text(encoding="utf-8")
        main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        storage = (ROOT / "backend/app/services/storage.py").read_text(encoding="utf-8")

        self.assertIn("build_storage(storage_config_from_settings(settings))", main)
        self.assertIn("class S3Storage", storage)
        self.assertIn("FileStorage", storage)
        self.assertIn("do **not** prove that an R2 bucket", threat_model)
        self.assertIn("Those remain GCP-004 gates", threat_model)

    def test_runbook_records_local_docker_evidence_and_readiness_limit(self) -> None:
        runbook = RUNBOOK.read_text(encoding="utf-8")

        self.assertIn("nebula-gcp001-api-dockercheck:912e208", runbook)
        self.assertIn("/live` returned `200", runbook)
        self.assertIn("/ready` returned `503", runbook)
        self.assertRegex(
            runbook, r"positive\s+database-backed readiness remains unproven"
        )


if __name__ == "__main__":
    unittest.main()
