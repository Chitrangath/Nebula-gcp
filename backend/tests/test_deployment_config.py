"""Semantic checks for the GCP demo deployment interface."""

import json
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
GCP_ROOT = REPOSITORY_ROOT / "deploy" / "gcp-demo"
SERVICE_TEMPLATE = GCP_ROOT / "cloud-run-service.template.yaml"
FOUNDATION_WIZARD = REPOSITORY_ROOT / "scripts" / "gcp004_foundation_deploy_wizard.sh"
LAPTOP_RUNTIME_WIZARD = REPOSITORY_ROOT / "scripts" / "gcp006_laptop_demo_runtime_wizard.sh"
pytestmark = pytest.mark.asyncio


def _cloud_run_service() -> dict[str, Any]:
    """Load the JSON-compatible Cloud Run service template."""
    return json.loads(SERVICE_TEMPLATE.read_text(encoding="utf-8"))


async def test_container_runs_locked_backend_as_non_root() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER app" in dockerfile
    assert 'CMD ["uv", "run", "--no-sync", "uvicorn"' in dockerfile
    assert '"--host", "0.0.0.0", "--port", "8000"' in dockerfile
    assert ".env" not in dockerfile
    assert ".env" in dockerignore
    assert ".env.*" in dockerignore


async def test_cloud_run_profile_is_api_only_and_scales_to_zero() -> None:
    service = _cloud_run_service()
    revision = service["spec"]["template"]
    annotations = revision["metadata"]["annotations"]
    containers = revision["spec"]["containers"]
    container = containers[0]
    environment = {item["name"]: item for item in container["env"]}

    assert service["kind"] == "Service"
    assert annotations["autoscaling.knative.dev/minScale"] == "0"
    assert annotations["autoscaling.knative.dev/maxScale"] == "2"
    assert annotations["run.googleapis.com/cpu-throttling"] == "true"
    assert [item["name"] for item in containers] == ["api"]
    assert environment["RUNNERS_ENABLED"]["value"] == "false"
    assert environment["STORAGE_ADAPTER"]["value"] == "s3"
    assert container["resources"]["limits"] == {"cpu": "1", "memory": "512Mi"}


async def test_cloud_run_uses_digest_placeholder_secrets_and_readiness() -> None:
    service = _cloud_run_service()
    revision_spec = service["spec"]["template"]["spec"]
    container = revision_spec["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == "__OWNER_APPROVED_IMAGE_DIGEST__"
    assert revision_spec["serviceAccountName"] == "__OWNER_APPROVED_RUNTIME_SERVICE_ACCOUNT__"
    assert "${PORT:?Cloud Run PORT is required}" in " ".join(container["args"])
    assert container["ports"] == [{"name": "http1", "containerPort": 8080}]
    assert container["startupProbe"]["httpGet"] == {"path": "/ready", "port": 8080}
    for name in (
        "DATABASE_URL",
        "JWT_SECRET",
        "ARBITRUM_SEPOLIA_RPC",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ):
        assert "value" not in environment[name]
        assert "secretKeyRef" in environment[name]["valueFrom"]


async def test_legacy_oci_and_fly_deployment_profiles_are_absent() -> None:
    assert not (REPOSITORY_ROOT / "deploy" / "oci").exists()
    assert not (BACKEND_ROOT / "fly.toml").exists()


async def test_foundation_wizard_preserves_cost_secret_and_runtime_guards() -> None:
    wizard = FOUNDATION_WIZARD.read_text(encoding="utf-8")

    assert "I-ACCEPT-COST-RISK" in wizard
    assert "budgets are not hard caps" in wizard
    assert "BUDGET-REVIEWED" in wizard
    assert "numbered Secret Manager" in wizard
    assert "roles/secretmanager.secretAccessor" in wizard
    assert "require_digest_image" in wizard
    assert "RUNNERS_ENABLED=false" in wizard
    assert "PUBLIC_R2=false" in wizard
    assert "DELETE-DATABASE-PROBE" in wizard


async def test_laptop_runtime_is_supervised_reversible_and_not_cloud_hosted() -> None:
    wizard = LAPTOP_RUNTIME_WIZARD.read_text(encoding="utf-8")

    assert "--status | --stop" in wizard
    assert "chmod 600" in wizard
    assert "RUNNERS_ENABLED false" in wizard
    assert "START-${name^^}" in wizard
    assert "kill -TERM" in wizard
    assert "CLOUD-RUN-API-ONLY" in wizard
    assert "Controlled processes are laptop-only" in wizard
