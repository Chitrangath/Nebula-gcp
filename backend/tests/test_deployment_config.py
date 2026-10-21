"""Semantic checks for the zero-cost OCI deployment interface."""

import json
import os
import pathlib
import subprocess

import pytest

BACKEND_ROOT = pathlib.Path(__file__).parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
OCI_ROOT = REPOSITORY_ROOT / "deploy" / "oci"
OWNER_DEMO_WIZARD = REPOSITORY_ROOT / "scripts" / "be002_owner_operated_demo_wizard.sh"


def _normalized_compose() -> dict[str, object]:
    """Return Docker Compose's normalized model instead of inspecting YAML text."""
    environment = os.environ.copy()
    environment["BACKEND_ENV_FILE"] = str(OCI_ROOT / "backend.env.example")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(OCI_ROOT / ".env.example"),
            "-f",
            str(OCI_ROOT / "compose.yaml"),
            "--profile",
            "runners",
            "config",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_container_runs_locked_backend_as_non_root():
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text()
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text().splitlines()

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER app" in dockerfile
    assert 'CMD ["uv", "run", "--no-sync", "uvicorn"' in dockerfile
    assert '"--host", "0.0.0.0", "--port", "8000"' in dockerfile
    assert ".env" not in dockerfile
    assert ".env" in dockerignore
    assert ".env.*" in dockerignore


@pytest.mark.asyncio
async def test_oci_compose_keeps_api_private_and_defines_every_runtime_runner():
    compose = _normalized_compose()
    services = compose["services"]
    api = services["api"]
    caddy = services["caddy"]

    assert api["expose"] == ["8000"]
    assert "ports" not in api
    assert caddy["ports"] == [
        {"mode": "ingress", "target": 80, "published": "80", "protocol": "tcp"},
        {"mode": "ingress", "target": 443, "published": "443", "protocol": "tcp"},
    ]
    assert "/ready" in " ".join(api["healthcheck"]["test"])

    for runner in ("receipts", "assignment", "settlement", "events", "reconciliation"):
        service = services[f"runner-{runner}"]
        assert service["command"] == ["uv", "run", "--no-sync", "python", "-m", "app.runners", runner]
        assert service["profiles"] == ["runners"]
        assert service["restart"] == "unless-stopped"

    expected_environment = {"DATABASE_URL", "JWT_SECRET", "FRONTEND_URL", "RUNNERS_ENABLED"}
    for name, service in services.items():
        if name != "caddy":
            assert expected_environment <= service["environment"].keys()


@pytest.mark.asyncio
async def test_oci_proxy_terminates_tls_and_forwards_only_to_internal_api():
    compose = _normalized_compose()
    caddyfile = (OCI_ROOT / "Caddyfile").read_text()

    assert "caddy" in compose["services"]
    assert "api:8000" in caddyfile
    assert "{$BACKEND_HOSTNAME}" in caddyfile
    assert "header" in caddyfile
    assert "Strict-Transport-Security" in caddyfile


@pytest.mark.asyncio
async def test_fly_configuration_is_removed_from_zero_cost_deployment():
    assert not (BACKEND_ROOT / "fly.toml").exists()


@pytest.mark.asyncio
async def test_owner_wizard_refuses_paid_oci_resources_and_preserves_secret_files():
    wizard = (REPOSITORY_ROOT / "scripts" / "be002_production_auth_wizard.sh").read_text()

    assert "Always Free eligible" in wizard
    assert "Do not click Upgrade" in wizard
    assert "exactly 1 OCPU and 6 GB RAM" in wizard
    assert "OCI_CPUS == 1" in wizard
    assert "OCI_MEMORY_KB >= 5500000" in wizard
    assert "OCI_MEMORY_KB <= 6500000" in wizard
    assert "2 OCPUs and 12 GB RAM" not in wizard
    assert "backend.env" in wizard
    assert "chmod 600" in wizard
    assert "RUNNERS_ENABLED='false'" in wizard
    assert "flyctl" not in wizard
    assert "fly.toml" not in wizard


@pytest.mark.asyncio
async def test_owner_operated_demo_wizard_is_an_isolated_reversible_profile():
    """The temporary laptop route must not weaken or replace the OCI profile."""
    wizard = OWNER_DEMO_WIZARD.read_text()

    assert "TOTAL_STAGES=7" in wizard
    assert "nebula-owner-demo" in wizard
    assert "--project-name \"$COMPOSE_PROJECT\"" in wizard
    assert "deploy/oci/compose.yaml" in wizard
    assert "RUNNERS_ENABLED='false'" in wizard
    assert "backend.env" in wizard
    assert "chmod 600" in wizard
    assert "DuckDNS" in wizard
    assert "CGNAT" in wizard
    assert "Cloudflare Quick Tunnels" in wizard
    assert 'DUCKDNS_DOMAIN="${BACKEND_HOSTNAME%.duckdns.org}"' in wizard
    assert 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip=%s"' in wizard
    assert 'TOKEN_ENCODED=$(urlencode "$DUCKDNS_TOKEN")' in wizard
    assert "Get-Clipboard -Raw" in wizard
    assert "DuckDNS rejected the update" in wizard
    assert "frontend/vercel.json" in wizard
    assert '"source": "/api/v1/:path*"' in wizard
    assert "be002_production_auth_wizard.sh" in wizard
