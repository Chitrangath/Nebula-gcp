"""Public CLI contract for the Ubuntu/WSL E2E setup wizard."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIZARD = ROOT / "scripts/setup_e2e_wizard.sh"
README = ROOT / "README.md"


def run_wizard(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WIZARD), *arguments],
        cwd=ROOT,
        env={**os.environ, "NO_COLOR": "1"},
        check=False,
        capture_output=True,
        text=True,
    )


class SetupE2EWizardContractTest(unittest.TestCase):
    def test_help_documents_every_public_mode(self) -> None:
        result = run_wizard("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        for mode in ("--check", "--plan", "--install", "--verify"):
            self.assertIn(mode, result.stdout)

    def test_plan_is_non_mutating_and_orders_all_setup_stages(self) -> None:
        result = run_wizard("--plan")

        self.assertEqual(result.returncode, 0, result.stderr)
        stages = (
            "Ubuntu/WSL host validation",
            "base operating-system packages",
            "Python 3.12 and uv",
            "Node.js 24 LTS and npm",
            "Foundry, Forge, Cast, and Anvil",
            "Docker Engine, Compose, and PostgreSQL",
            "repository dependencies",
            "Playwright Chromium",
            "local E2E environment",
            "contract build and deployed-artifact validation",
            "optional NVIDIA/CUDA readiness",
            "complete E2E readiness verification",
        )
        positions = [result.stdout.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))

    def test_check_reports_every_required_tool_without_installing(self) -> None:
        result = run_wizard("--check")

        self.assertIn(result.returncode, (0, 1))
        combined = result.stdout + result.stderr
        for tool in (
            "git",
            "curl",
            "uv",
            "python3.12",
            "node",
            "npm",
            "forge",
            "cast",
            "anvil",
            "docker",
            "docker compose",
        ):
            self.assertIn(tool, combined)
        self.assertNotIn("apt-get update", combined)

    def test_install_and_verify_require_an_interactive_terminal(self) -> None:
        for mode in ("--install", "--verify"):
            result = run_wizard(mode)
            self.assertEqual(result.returncode, 2)
            self.assertIn("interactive terminal", result.stderr)

    def test_script_guards_privileged_and_remote_actions(self) -> None:
        text = WIZARD.read_text(encoding="utf-8")

        self.assertIn("confirm", text)
        self.assertIn("sudo apt-get", text)
        self.assertIn("https://docs.docker.com/engine/install/ubuntu/", text)
        self.assertIn("https://getfoundry.sh/getting-started/installation", text)
        self.assertIn("npx playwright install --with-deps chromium", text)
        self.assertNotIn("curl -L https://foundry.paradigm.xyz | bash", text)
        self.assertNotIn("curl -fsSL https://get.docker.com |", text)
        self.assertIn('x86_64) NODE_PLATFORM_ARCH="x64"', text)
        self.assertIn('aarch64) NODE_PLATFORM_ARCH="arm64"', text)
        self.assertIn("docker compose version", text)
        self.assertIn("docker info", text)
        self.assertIn("Docker installation or repair", text)
        self.assertIn("required stage declined", text)
        self.assertIn("BE002_FRONTEND_ORIGIN", text)
        self.assertIn("torch.cuda.is_available", text)
        self.assertIn("POSTGRES_PASSWORD=nebula_e2e", text)
        self.assertIn('host_ip" == "127.0.0.1', text)
        self.assertIn('.HostConfig.PortBindings "5432/tcp"', text)
        self.assertNotIn('.NetworkSettings.Ports "5432/tcp"', text)
        self.assertIn("chromium.launch", text)

    def test_readme_links_the_repeatable_setup_path(self) -> None:
        readme = README.read_text(encoding="utf-8")

        self.assertIn("scripts/setup_e2e_wizard.sh --check", readme)
        self.assertIn("scripts/setup_e2e_wizard.sh --install", readme)
        self.assertIn("scripts/setup_e2e_wizard.sh --verify", readme)

    def test_foundry_dependencies_include_a_direct_pinned_invariant_library(self) -> None:
        wizard = WIZARD.read_text(encoding="utf-8")
        foundry_config = (ROOT / "contracts/foundry.toml").read_text(encoding="utf-8")
        contract_tests = (
            ROOT / "contracts/test/NebulaVerifiableAI.t.sol"
        ).read_text(encoding="utf-8")

        self.assertIn("--branch v1.9.7 --depth 1", wizard)
        self.assertIn("https://github.com/foundry-rs/forge-std.git", wizard)
        self.assertIn(
            'forge-std/=lib/openzeppelin-contracts/lib/forge-std/src/',
            foundry_config,
        )
        self.assertIn('import "forge-std/Test.sol";', contract_tests)
        self.assertIn("contract NebulaStatefulInvariantTest is Test", contract_tests)


if __name__ == "__main__":
    unittest.main()
