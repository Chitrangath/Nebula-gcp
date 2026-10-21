"""Regression tests for deployment-secret and Foundry-journal ignore rules."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DeploymentGitignoreTest(unittest.TestCase):
    def is_ignored(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", path],
            cwd=ROOT,
            check=False,
        )
        self.assertIn(result.returncode, (0, 1))
        return result.returncode == 0

    def test_ignores_foundry_broadcast_journals(self) -> None:
        self.assertTrue(
            self.is_ignored("contracts/broadcast/Deploy.s.sol/421614/run-latest.json")
        )

    def test_ignores_environment_secret_variants_at_any_depth(self) -> None:
        self.assertTrue(self.is_ignored(".env.production"))
        self.assertTrue(self.is_ignored("backend/.env.sepolia"))
        self.assertTrue(self.is_ignored("contracts/.env.deploy"))

    def test_keeps_environment_examples_trackable(self) -> None:
        self.assertFalse(self.is_ignored(".env.example"))
        self.assertFalse(self.is_ignored("backend/.env.example"))


if __name__ == "__main__":
    unittest.main()
