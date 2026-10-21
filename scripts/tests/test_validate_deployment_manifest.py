"""Behavior tests for the public deployment-manifest validator CLI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts/validate_deployment_manifest.py"
SCHEMA = ROOT / "contracts/deployments/deployment-manifest.schema.json"


def valid_manifest() -> dict[str, object]:
    contract = "0x1111111111111111111111111111111111111111"
    return {
        "network": "arbitrum-sepolia",
        "chain_id": 421614,
        "contract_address": contract,
        "usdc_address": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        "owner_address": "0x2222222222222222222222222222222222222222",
        "verifier_address": "0x3333333333333333333333333333333333333333",
        "deployment_transaction_hash": "0x" + "44" * 32,
        "deployment_block": 123456,
        "deployed_at_utc": "2026-09-09T05:00:00Z",
        "source_commit": "5" * 40,
        "abi_sha256": "66" * 32,
        "runtime_template_sha256": "77" * 32,
        "on_chain_code_sha256": "88" * 32,
        "compiler": "0.8.20+commit.a1b79de6",
        "optimizer_enabled": True,
        "optimizer_runs": 200,
        "via_ir": True,
        "evm_version": "shanghai",
        "explorer_url": f"https://sepolia.arbiscan.io/address/{contract}",
        "source_verified": True,
    }


class DeploymentManifestValidatorTest(unittest.TestCase):
    def run_validator(
        self, manifest: dict[str, object]
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def assert_rejected(self, manifest: dict[str, object], expected_error: str) -> None:
        result = self.run_validator(manifest)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(expected_error, result.stderr)

    def test_accepts_complete_public_manifest_with_distinct_runtime_hashes(
        self,
    ) -> None:
        result = self.run_validator(valid_manifest())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "deployment manifest is valid\n")

    def test_rejects_missing_required_field(self) -> None:
        manifest = valid_manifest()
        del manifest["deployment_transaction_hash"]

        self.assert_rejected(
            manifest, "missing required field: deployment_transaction_hash"
        )

    def test_rejects_placeholder_as_deployed_claim(self) -> None:
        manifest = valid_manifest()
        manifest["contract_address"] = "0x..."

        self.assert_rejected(
            manifest, "contract_address must be a nonzero 20-byte hex address"
        )

    def test_rejects_wrong_network_and_chain(self) -> None:
        manifest = valid_manifest()
        manifest["network"] = "arbitrum-one"
        manifest["chain_id"] = 42161

        self.assert_rejected(manifest, "network must equal arbitrum-sepolia")
        self.assert_rejected(manifest, "chain_id must equal 421614")

    def test_rejects_wrong_address_and_explorer_binding(self) -> None:
        manifest = valid_manifest()
        manifest["owner_address"] = "0x1234"

        self.assert_rejected(
            manifest, "owner_address must be a nonzero 20-byte hex address"
        )

        manifest = valid_manifest()
        manifest["usdc_address"] = "0x9999999999999999999999999999999999999999"
        self.assert_rejected(
            manifest, "usdc_address must equal Arbitrum Sepolia Circle USDC"
        )

        manifest = valid_manifest()
        manifest["usdc_address"] = str(manifest["usdc_address"]).lower()
        self.assert_rejected(
            manifest, "usdc_address must equal Arbitrum Sepolia Circle USDC"
        )

        manifest = valid_manifest()
        manifest["explorer_url"] = (
            "https://sepolia.arbiscan.io/address/0x2222222222222222222222222222222222222222"
        )
        self.assert_rejected(manifest, "explorer_url must reference contract_address")

    def test_rejects_wrong_transaction_and_sha256_hashes(self) -> None:
        manifest = valid_manifest()
        manifest["deployment_transaction_hash"] = "0x1234"
        manifest["abi_sha256"] = "0x" + "66" * 32

        self.assert_rejected(
            manifest, "deployment_transaction_hash must be a nonzero 32-byte hex hash"
        )
        self.assert_rejected(
            manifest,
            "abi_sha256 must be 64 lowercase hexadecimal characters without 0x",
        )

    def test_rejects_missing_receipt_block_and_verification_evidence(self) -> None:
        manifest = valid_manifest()
        manifest["deployment_block"] = 0
        manifest["deployed_at_utc"] = "..."
        manifest["source_verified"] = False

        self.assert_rejected(manifest, "deployment_block must be a positive integer")
        self.assert_rejected(
            manifest, "deployed_at_utc must be an ISO-8601 UTC timestamp ending in Z"
        )
        self.assert_rejected(manifest, "source_verified must be true")

        manifest = valid_manifest()
        manifest["deployed_at_utc"] = "2026-09-09T05Z"
        self.assert_rejected(
            manifest, "deployed_at_utc must be an ISO-8601 UTC timestamp ending in Z"
        )

    def test_rejects_equal_runtime_template_and_on_chain_hashes(self) -> None:
        manifest = valid_manifest()
        manifest["on_chain_code_sha256"] = manifest["runtime_template_sha256"]

        self.assert_rejected(
            manifest,
            "on_chain_code_sha256 must differ from runtime_template_sha256 because USDC is immutable",
        )

    def test_rejects_wrong_source_and_compiler_settings(self) -> None:
        manifest = valid_manifest()
        manifest.update(
            {
                "source_commit": "main",
                "compiler": "0.8.21",
                "optimizer_enabled": False,
                "optimizer_runs": 999,
                "via_ir": False,
                "evm_version": "paris",
            }
        )

        for error in (
            "source_commit must be a 40-character Git commit hash",
            "compiler must equal 0.8.20+commit.a1b79de6",
            "optimizer_enabled must be true",
            "optimizer_runs must equal 200",
            "via_ir must be true",
            "evm_version must equal shanghai",
        ):
            self.assert_rejected(manifest, error)

    def test_rejects_secret_like_and_unknown_fields(self) -> None:
        manifest = valid_manifest()
        manifest["deployer_private_key"] = "0x" + "99" * 32
        self.assert_rejected(
            manifest, "secret-like field is forbidden: deployer_private_key"
        )

        manifest = valid_manifest()
        manifest["notes"] = "unreviewed"
        self.assert_rejected(manifest, "unexpected field: notes")

    def test_rejects_malformed_json_and_non_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text("{", encoding="utf-8")
            malformed = subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            path.write_text("[]", encoding="utf-8")
            non_object = subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(malformed.returncode, 1)
        self.assertIn("manifest is not valid JSON", malformed.stderr)
        self.assertEqual(non_object.returncode, 1)
        self.assertIn("manifest root must be a JSON object", non_object.stderr)

    def test_schema_declares_exact_public_interface(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(set(schema["required"]), set(valid_manifest()))
        self.assertEqual(set(schema["properties"]), set(valid_manifest()))
        self.assertFalse(schema["additionalProperties"])

        definitions = schema["$defs"]
        self.assertIsNone(
            re.fullmatch(definitions["address"]["pattern"], "0x" + "0" * 40)
        )
        self.assertIsNone(
            re.fullmatch(definitions["transactionHash"]["pattern"], "0x" + "0" * 64)
        )
        self.assertIsNone(re.fullmatch(definitions["sha256"]["pattern"], "0" * 64))
        self.assertIsNone(
            re.fullmatch(schema["properties"]["source_commit"]["pattern"], "0" * 40)
        )


if __name__ == "__main__":
    unittest.main()
