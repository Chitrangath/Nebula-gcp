"""Static and non-mutating behavior contracts for the owner deployment wizards."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from eth_account import Account

from scripts.gcp004_storage_exchange_probe import validate_roles

ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = ROOT / "scripts/gcp004_foundation_deploy_wizard.sh"
CUTOVER = ROOT / "scripts/gcp005_vercel_browser_cutover_wizard.sh"
LAPTOP = ROOT / "scripts/gcp006_laptop_demo_runtime_wizard.sh"
LIBRARY = ROOT / "scripts/lib/nebula_owner_wizard.sh"
RENDERER = ROOT / "scripts/render_gcp_demo_config.py"
DB_PROBE_RENDERER = ROOT / "scripts/render_gcp_db_unavailable_probe.py"
STORAGE_EXCHANGE_PROBE = ROOT / "scripts/gcp004_storage_exchange_probe.py"
VALIDATOR = ROOT / "scripts/validate_gcp_demo_config.py"
WIZARDS = (FOUNDATION, CUTOVER, LAPTOP)


def run_wizard(
    path: Path, *arguments: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(path), *arguments],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        check=False,
        capture_output=True,
        text=True,
    )


class SharedWizardContractTest(unittest.TestCase):
    def test_each_wizard_exposes_non_mutating_check_plan_and_help(self) -> None:
        for wizard in WIZARDS:
            for mode in ("--check", "--plan", "--help"):
                result = run_wizard(wizard, mode)
                self.assertEqual(
                    result.returncode, 0, f"{wizard.name} {mode}: {result.stderr}"
                )

    def test_shared_library_refuses_xtrace_and_protects_secret_files(self) -> None:
        text = LIBRARY.read_text(encoding="utf-8")
        self.assertIn('if [[ "$-" == *x* ]]', text)
        self.assertRegex(text, r"read\s+-rs")
        self.assertIn('chmod 600 "$path"', text)
        self.assertIn("umask 077", text)
        self.assertNotRegex(
            text,
            r"(?:echo|printf).*\$\{?[^}\n]*(?:SECRET|TOKEN|PRIVATE_KEY|DATABASE_URL)",
        )

    def test_run_modes_require_explicit_interactive_terminal(self) -> None:
        for wizard in WIZARDS:
            result = run_wizard(wizard, "--run")
            self.assertEqual(result.returncode, 2)
            self.assertIn("interactive terminal", result.stderr)


class FoundationWizardContractTest(unittest.TestCase):
    def test_foundation_bootstrap_is_interactive_and_owner_gated(self) -> None:
        result = run_wizard(FOUNDATION, "--bootstrap")

        self.assertEqual(result.returncode, 2)
        self.assertIn("interactive terminal", result.stderr)

        text = FOUNDATION.read_text(encoding="utf-8")
        self.assertIn("packages.cloud.google.com/apt", text)
        self.assertIn("INSTALL-GCLOUD", text)
        self.assertIn("GCLOUD-LOGIN", text)
        self.assertIn("gcloud auth login --no-launch-browser", text)
        self.assertGreaterEqual(text.count("install -o root -g root -m 0644"), 2)
        self.assertLess(
            text.index("repair existing Google Cloud apt signing-key permissions"),
            text.index("refresh Ubuntu package metadata"),
        )
        self.assertNotIn("gcloud init", text)

    def test_foundation_help_exposes_bootstrap_separately_from_deployment(self) -> None:
        result = run_wizard(FOUNDATION, "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--bootstrap", result.stdout)
        self.assertIn("--run", result.stdout)

    def test_foundation_check_uses_the_active_repository_metadata(self) -> None:
        result = run_wizard(FOUNDATION, "--check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Not a git repository", result.stderr)
        self.assertRegex(
            result.stdout,
            r"worktree is (?:clean|dirty)",
        )

    def test_foundation_plan_has_all_thirteen_stages_in_order(self) -> None:
        result = run_wizard(FOUNDATION, "--plan")
        stages = (
            "repository integrity and immutable source",
            "project, region, billing, and cost-risk acknowledgement",
            "budget alerts and cost review",
            "required Google API enablement",
            "private Cloudflare R2 bucket creation",
            "bucket-scoped R2 object read/write token",
            "runtime service account and least-privilege IAM",
            "numbered Secret Manager secrets",
            "immutable image build, scan, upload, and digest",
            "API-only Cloud Run deployment",
            "direct health plus isolated database-unavailable /ready=503",
            "Cloud Run and laptop private-object exchange",
            "stop before Vercel, DNS, or browser routing",
        )
        positions = [result.stdout.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_foundation_has_official_docs_before_owner_capture_and_confirmation_gates(
        self,
    ) -> None:
        text = FOUNDATION.read_text(encoding="utf-8")
        for domain in (
            "console.cloud.google.com",
            "developers.cloudflare.com",
            "cloud.google.com",
        ):
            self.assertIn(domain, text)
        self.assertLess(text.index("open_url"), text.index("ask_public"))
        self.assertIn("confirm_action", text)
        self.assertIn("ask_secret", text)

    def test_foundation_cannot_mutate_vercel_or_enable_cloud_run_runners(self) -> None:
        text = FOUNDATION.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^\s*(?:run_command\s+)?vercel\b")
        self.assertNotIn("vercel deploy", text)
        self.assertIn("RUNNERS_ENABLED=false", text)
        self.assertIn("STORAGE_ADAPTER=s3", text)
        self.assertNotRegex(text, r"RUNNERS_ENABLED=(?:true|1)")
        self.assertIn("validate_gcp_demo_config.py", text)

    def test_foundation_refuses_placeholders_file_storage_and_mutable_images(
        self,
    ) -> None:
        text = FOUNDATION.read_text(encoding="utf-8")
        self.assertIn("reject_placeholder", text)
        self.assertIn("require_exact STORAGE_ADAPTER s3", text)
        self.assertIn("require_exact RUNNERS_ENABLED false", text)
        self.assertRegex(text, r"sha256:")
        self.assertIn("public R2 access must remain disabled", text)

    def test_foundation_executes_and_removes_isolated_database_failure_probe(
        self,
    ) -> None:
        text = FOUNDATION.read_text(encoding="utf-8")

        self.assertIn("render_gcp_db_unavailable_probe.py", text)
        self.assertIn("DATABASE-FAILURE-PROBE", text)
        self.assertIn("DELETE-DATABASE-PROBE", text)
        self.assertIn("expected 503", text)
        self.assertIn("gcloud run services delete", text)

    def test_foundation_executes_storage_exchange_instead_of_accepting_pasted_hashes(
        self,
    ) -> None:
        text = FOUNDATION.read_text(encoding="utf-8")

        self.assertIn("gcp004_storage_exchange_probe.py", text)
        self.assertIn("RUN-STORAGE-EXCHANGE", text)
        self.assertIn(
            "net003_sepolia_smoke.py",
            STORAGE_EXCHANGE_PROBE.read_text(encoding="utf-8"),
        )
        self.assertNotIn("ask_public input_hash", text)
        self.assertNotIn("ask_public result_hash", text)
        self.assertIn('"input_sha256"', text)
        self.assertIn('"result_sha256"', text)

    def test_storage_exchange_probe_fails_closed_without_protected_configuration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    str(ROOT / "backend/.venv/bin/python"),
                    str(STORAGE_EXCHANGE_PROBE),
                    "--config-dir",
                    directory,
                    "--output",
                    str(Path(directory) / "evidence.json"),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing protected configuration value", result.stderr)

    def test_storage_exchange_probe_enforces_cleanup_and_role_isolation(self) -> None:
        probe_text = STORAGE_EXCHANGE_PROBE.read_text(encoding="utf-8")
        smoke_text = (ROOT / "scripts/net003_sepolia_smoke.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("for address in (ai_user, provider, worker, executor)", probe_text)
        self.assertIn("process.terminate()", probe_text)
        self.assertIn("signal.signal(signal.SIGTERM, handle_termination)", smoke_text)
        self.assertIn("process_base_environment()", smoke_text)
        self.assertIn("LOG_DIR.chmod(0o700)", smoke_text)
        self.assertIn("log_path.chmod(0o600)", smoke_text)
        self.assertIn("storage.get_object(job.input_file_key)", smoke_text)

    def test_storage_exchange_probe_rejects_colliding_roles(self) -> None:
        keys = {
            name: f"0x{number:064x}"
            for number, name in enumerate(
                (
                    "GCP004_AI_USER_PRIVATE_KEY",
                    "GCP004_PROVIDER_PRIVATE_KEY",
                    "GCP004_WORKER_PRIVATE_KEY",
                    "GCP004_EXECUTOR_PRIVATE_KEY",
                ),
                start=1,
            )
        }
        keys["CONTRACT_VERIFIER_ADDRESS"] = Account.from_key(
            keys["GCP004_EXECUTOR_PRIVATE_KEY"]
        ).address
        keys["GCP004_WORKER_PRIVATE_KEY"] = keys["GCP004_PROVIDER_PRIVATE_KEY"]

        with self.assertRaisesRegex(ValueError, "identities must be distinct"):
            validate_roles(keys)


class CutoverWizardContractTest(unittest.TestCase):
    def test_cutover_plan_preserves_same_origin_browser_auth(self) -> None:
        result = run_wizard(CUTOVER, "--plan")
        for statement in (
            "GCP-004 sanitized direct acceptance evidence",
            "exact frontend production origin",
            "same-origin /api/v1/* rewrite",
            "owner confirmation before Vercel mutation",
            "Vercel frontend deployment",
            "real browser authentication acceptance",
            "immediate frontend routing rollback",
            "module-memory access token",
            "HttpOnly, Secure, SameSite=Strict",
            "Origin == FRONTEND_URL",
        ):
            self.assertIn(statement, result.stdout)

    def test_cutover_refuses_without_foundation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_wizard(
                CUTOVER,
                "--validate-evidence",
                env={"NEBULA_GCP_STATE_DIR": directory},
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("GCP-004 sanitized direct acceptance evidence", result.stderr)

    def test_cutover_uses_reviewed_rewrite_template_and_never_cross_origin_design(
        self,
    ) -> None:
        text = CUTOVER.read_text(encoding="utf-8")
        self.assertIn("deploy/gcp-demo/vercel-rewrite.template.json", text)
        self.assertIn("validate_gcp_demo_config.py", text)
        self.assertNotIn("localStorage", text)
        self.assertNotIn("sessionStorage", text)


class LaptopWizardContractTest(unittest.TestCase):
    def test_laptop_plan_orders_validation_prepare_start_and_stop(self) -> None:
        result = run_wizard(LAPTOP, "--plan")
        stages = (
            "local Docker, Python, Node, and clean configuration",
            "Cloud Run, Supabase, private R2, RPC, and contract connectivity",
            "separate worker, GPU provider, and Verifier identities",
            "prepare worker and five controlled runner commands",
            "confirm immediately before each process start",
            "safe status, stop, and cleanup",
            "no continuous runners on Cloud Run",
        )
        positions = [result.stdout.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_laptop_does_not_start_processes_in_check_or_plan_modes(self) -> None:
        text = LAPTOP.read_text(encoding="utf-8")
        self.assertIn("Processes are prepared but not started by default", text)
        self.assertIn("confirm_action", text)
        self.assertIn("receipt", text)
        self.assertIn("assignment", text)
        self.assertIn("settlement", text)
        self.assertIn("event", text)
        self.assertIn("reconciliation", text)
        self.assertNotRegex(
            text,
            r"(?m)^\s*(?:python|uv|docker compose).*(?:runner|worker).*(?:&|--detach)\s*$",
        )


class RenderedConfigurationContractTest(unittest.TestCase):
    def test_database_failure_probe_is_isolated_and_uses_the_same_image(self) -> None:
        source = {
            "apiVersion": "serving.knative.dev/v1",
            "kind": "Service",
            "metadata": {
                "name": "nebula-api",
                "annotations": {"run.googleapis.com/ingress": "all"},
            },
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "autoscaling.knative.dev/minScale": "0",
                            "autoscaling.knative.dev/maxScale": "2",
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "api",
                                "image": "us-central1-docker.pkg.dev/project/nebula/api@sha256:"
                                + "a" * 64,
                                "env": [
                                    {
                                        "name": "DATABASE_URL",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "database",
                                                "key": "1",
                                            }
                                        },
                                    },
                                    {
                                        "name": "JWT_SECRET",
                                        "valueFrom": {
                                            "secretKeyRef": {"name": "jwt", "key": "1"}
                                        },
                                    },
                                ],
                                "startupProbe": {
                                    "httpGet": {"path": "/ready", "port": 8080}
                                },
                            }
                        ]
                    },
                },
                "traffic": [{"latestRevision": True, "percent": 100}],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "service.json"
            output_path = Path(directory) / "probe.json"
            source_path.write_text(json.dumps(source), encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(DB_PROBE_RENDERER),
                    "--service",
                    str(source_path),
                    "--output",
                    str(output_path),
                    "--probe-service",
                    "nebula-api-db-probe",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            probe = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(probe["metadata"]["name"], "nebula-api-db-probe")
            container = probe["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(
                container["image"],
                source["spec"]["template"]["spec"]["containers"][0]["image"],
            )
            self.assertEqual(container["startupProbe"]["httpGet"]["path"], "/live")
            environment = {item["name"]: item for item in container["env"]}
            self.assertEqual(
                environment["DATABASE_URL"],
                {
                    "name": "DATABASE_URL",
                    "value": "postgresql+asyncpg://probe:probe@127.0.0.1:1/unavailable",
                },
            )
            self.assertIn("valueFrom", environment["JWT_SECRET"])
            self.assertEqual(
                probe["spec"]["template"]["metadata"]["annotations"][
                    "autoscaling.knative.dev/maxScale"
                ],
                "1",
            )

    def test_renderer_fails_closed_then_produces_validator_accepted_service(
        self,
    ) -> None:
        values = {
            "CLOUD_RUN_SERVICE": "nebula-demo-api",
            "RUNTIME_SERVICE_ACCOUNT": "nebula-api@example-project.iam.gserviceaccount.com",
            "IMAGE_DIGEST": "us-central1-docker.pkg.dev/example-project/nebula/api@sha256:"
            + "a" * 64,
            "FRONTEND_URL": "https://frontend.example.com",
            "DATABASE_SECRET_VERSION": "1",
            "JWT_SECRET_VERSION": "2",
            "RPC_SECRET_VERSION": "3",
            "R2_ACCESS_KEY_SECRET_VERSION": "4",
            "R2_SECRET_KEY_SECRET_VERSION": "5",
            "NEBULA_PAYMENT_CONTRACT": "0x" + "11" * 20,
            "CONTRACT_DEPLOYMENT_BLOCK": "123456",
            "CONTRACT_OWNER_ADDRESS": "0x" + "22" * 20,
            "CONTRACT_VERIFIER_ADDRESS": "0x" + "33" * 20,
            "R2_ACCOUNT_ID": "a" * 32,
            "R2_BUCKET_NAME": "nebula-demo-private",
            "OBJECT_STORAGE_PREFIX": "demo",
        }
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            output = Path(directory) / "service.json"
            config.mkdir(mode=0o700)
            refused = subprocess.run(
                [
                    "python3",
                    str(RENDERER),
                    "--config-dir",
                    str(config),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(refused.returncode, 0)
            for name, value in values.items():
                path = config / name
                path.write_text(value, encoding="utf-8")
                path.chmod(0o600)
            rendered = subprocess.run(
                [
                    "python3",
                    str(RENDERER),
                    "--config-dir",
                    str(config),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            service = json.loads(output.read_text(encoding="utf-8"))
            environment = {
                item["name"]: item
                for item in service["spec"]["template"]["spec"]["containers"][0]["env"]
            }
            self.assertEqual(environment["RUNNERS_ENABLED"]["value"], "false")
            self.assertEqual(environment["STORAGE_ADAPTER"]["value"], "s3")
            validated = subprocess.run(
                ["python3", str(VALIDATOR), "--service", str(output), "--service-only"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)


if __name__ == "__main__":
    unittest.main()
