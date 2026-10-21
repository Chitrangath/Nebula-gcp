#!/usr/bin/env python3
"""Validate a sanitized Nebula Arbitrum Sepolia deployment manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

NETWORK = "arbitrum-sepolia"
CHAIN_ID = 421_614
COMPILER = "0.8.20+commit.a1b79de6"
OPTIMIZER_RUNS = 200
EVM_VERSION = "shanghai"
ARBITRUM_SEPOLIA_USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
FIELDS = (
    "network",
    "chain_id",
    "contract_address",
    "usdc_address",
    "owner_address",
    "verifier_address",
    "deployment_transaction_hash",
    "deployment_block",
    "deployed_at_utc",
    "source_commit",
    "abi_sha256",
    "runtime_template_sha256",
    "on_chain_code_sha256",
    "compiler",
    "optimizer_enabled",
    "optimizer_runs",
    "via_ir",
    "evm_version",
    "explorer_url",
    "source_verified",
)
SECRET_FIELD_PARTS = (
    "api_key",
    "credential",
    "mnemonic",
    "password",
    "private_key",
    "rpc_url",
    "secret",
    "seed",
)
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
TRANSACTION_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class DuplicateFieldError(ValueError):
    """Raised when JSON contains a duplicate object key."""


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateFieldError(f"duplicate field: {key}")
        result[key] = value
    return result


def _is_nonzero_hex(value: object, pattern: re.Pattern[str]) -> bool:
    return (
        isinstance(value, str)
        and pattern.fullmatch(value) is not None
        and int(value, 16) != 0
    )


def _is_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    utc_offset = parsed.utcoffset()
    return utc_offset is not None and utc_offset.total_seconds() == 0


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return deterministic validation errors for one deployed manifest."""
    errors: list[str] = []

    for field in manifest:
        normalized = field.lower().replace("-", "_")
        if any(part in normalized for part in SECRET_FIELD_PARTS):
            errors.append(f"secret-like field is forbidden: {field}")
        elif field not in FIELDS:
            errors.append(f"unexpected field: {field}")

    for field in FIELDS:
        if field not in manifest:
            errors.append(f"missing required field: {field}")

    if manifest.get("network") != NETWORK:
        errors.append(f"network must equal {NETWORK}")
    if (
        type(manifest.get("chain_id")) is not int
        or manifest.get("chain_id") != CHAIN_ID
    ):
        errors.append(f"chain_id must equal {CHAIN_ID}")

    for field in (
        "contract_address",
        "usdc_address",
        "owner_address",
        "verifier_address",
    ):
        if not _is_nonzero_hex(manifest.get(field), ADDRESS_PATTERN):
            errors.append(f"{field} must be a nonzero 20-byte hex address")
    usdc_address = manifest.get("usdc_address")
    if (
        isinstance(usdc_address, str)
        and ADDRESS_PATTERN.fullmatch(usdc_address) is not None
        and usdc_address != ARBITRUM_SEPOLIA_USDC
    ):
        errors.append("usdc_address must equal Arbitrum Sepolia Circle USDC")

    if not _is_nonzero_hex(
        manifest.get("deployment_transaction_hash"), TRANSACTION_PATTERN
    ):
        errors.append("deployment_transaction_hash must be a nonzero 32-byte hex hash")
    if (
        type(manifest.get("deployment_block")) is not int
        or manifest.get("deployment_block", 0) <= 0
    ):
        errors.append("deployment_block must be a positive integer")
    if not _is_utc_timestamp(manifest.get("deployed_at_utc")):
        errors.append("deployed_at_utc must be an ISO-8601 UTC timestamp ending in Z")

    source_commit = manifest.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or COMMIT_PATTERN.fullmatch(source_commit) is None
        or int(source_commit, 16) == 0
    ):
        errors.append("source_commit must be a 40-character Git commit hash")

    for field in ("abi_sha256", "runtime_template_sha256", "on_chain_code_sha256"):
        value = manifest.get(field)
        if (
            not isinstance(value, str)
            or SHA256_PATTERN.fullmatch(value) is None
            or int(value, 16) == 0
        ):
            errors.append(
                f"{field} must be 64 lowercase hexadecimal characters without 0x"
            )
    if manifest.get("runtime_template_sha256") == manifest.get("on_chain_code_sha256"):
        errors.append(
            "on_chain_code_sha256 must differ from runtime_template_sha256 because USDC is immutable"
        )

    if manifest.get("compiler") != COMPILER:
        errors.append(f"compiler must equal {COMPILER}")
    if manifest.get("optimizer_enabled") is not True:
        errors.append("optimizer_enabled must be true")
    if (
        type(manifest.get("optimizer_runs")) is not int
        or manifest.get("optimizer_runs") != OPTIMIZER_RUNS
    ):
        errors.append(f"optimizer_runs must equal {OPTIMIZER_RUNS}")
    if manifest.get("via_ir") is not True:
        errors.append("via_ir must be true")
    if manifest.get("evm_version") != EVM_VERSION:
        errors.append(f"evm_version must equal {EVM_VERSION}")

    contract_address = manifest.get("contract_address")
    expected_explorer = (
        f"https://sepolia.arbiscan.io/address/{contract_address}"
        if isinstance(contract_address, str)
        else None
    )
    explorer_url = manifest.get("explorer_url")
    if (
        not isinstance(explorer_url, str)
        or expected_explorer is None
        or explorer_url.lower() != expected_explorer.lower()
    ):
        errors.append("explorer_url must reference contract_address")
    if manifest.get("source_verified") is not True:
        errors.append("source_verified must be true")

    return errors


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
        )
    except OSError as error:
        raise ValueError(f"cannot read manifest: {error}") from error
    except DuplicateFieldError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("manifest is not valid JSON") from error
    if not isinstance(value, dict):
        raise TypeError("manifest root must be a JSON object")
    return value


def main() -> int:
    """Run the deterministic manifest validator command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest", type=Path, help="path to a finalized public deployment manifest"
    )
    args = parser.parse_args()

    try:
        manifest = _load_manifest(args.manifest)
    except (TypeError, ValueError) as load_error:
        print(f"deployment manifest invalid: {load_error}", file=sys.stderr)
        return 1

    errors = validate_manifest(manifest)
    if errors:
        for validation_error in errors:
            print(f"deployment manifest invalid: {validation_error}", file=sys.stderr)
        return 1

    print("deployment manifest is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
