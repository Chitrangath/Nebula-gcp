#!/usr/bin/env python3
"""Run the bounded NET-003 journey against Cloud Run and emit sanitized hashes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts/net003_sepolia_smoke.py"
USDC = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"


def read_value(config_dir: Path, name: str) -> str:
    path = config_dir / name
    value = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if not value:
        raise ValueError(f"missing protected configuration value: {name}")
    return value


def validate_roles(values: dict[str, str]) -> tuple[str, str, str, str]:
    """Derive and require four distinct operator-controlled identities."""
    ai_user = Account.from_key(values["GCP004_AI_USER_PRIVATE_KEY"]).address
    provider = Account.from_key(values["GCP004_PROVIDER_PRIVATE_KEY"]).address
    worker = Account.from_key(values["GCP004_WORKER_PRIVATE_KEY"]).address
    executor = Account.from_key(values["GCP004_EXECUTOR_PRIVATE_KEY"]).address
    if executor.lower() != values["CONTRACT_VERIFIER_ADDRESS"].lower():
        raise ValueError(
            "executor private key does not match the deployed Verifier address"
        )
    if len({address.lower() for address in (ai_user, provider, worker, executor)}) != 4:
        raise ValueError(
            "AI user, provider, Worker signer, and Verifier identities must be distinct"
        )
    return ai_user, provider, worker, executor


def run_smoke(env: dict[str, str], error_log: Path, timeout: int = 900) -> str:
    """Run the bounded journey and retain its diagnostic stderr securely."""
    process = subprocess.Popen(
        [sys.executable, str(SMOKE)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        _write_error_log(error_log, stderr)
        raise RuntimeError(
            f"bounded live journey exceeded its 15-minute deadline; inspect {error_log}"
        ) from None
    _write_error_log(error_log, stderr)
    if process.returncode != 0:
        raise RuntimeError(f"bounded live journey failed; inspect {error_log}")
    return stdout


def _write_error_log(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--error-log", type=Path)
    args = parser.parse_args()

    try:
        values = {
            name: read_value(args.config_dir, name)
            for name in (
                "DATABASE_URL",
                "JWT_SECRET",
                "FRONTEND_URL",
                "ARBITRUM_SEPOLIA_RPC",
                "NEBULA_PAYMENT_CONTRACT",
                "CONTRACT_DEPLOYMENT_BLOCK",
                "CONTRACT_VERIFIER_ADDRESS",
                "R2_ACCOUNT_ID",
                "R2_BUCKET_NAME",
                "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY",
                "OBJECT_STORAGE_PREFIX",
                "CLOUD_RUN_ORIGIN",
                "GCP004_AI_USER_PRIVATE_KEY",
                "GCP004_PROVIDER_PRIVATE_KEY",
                "GCP004_WORKER_PRIVATE_KEY",
                "GCP004_EXECUTOR_PRIVATE_KEY",
            )
        }
        _, provider, worker, executor = validate_roles(values)

        env = dict(os.environ)
        env.update(values)
        env.update(
            {
                "NET003_CONFIG_FROM_ENV": "true",
                "NET003_START_LOCAL_API": "false",
                "NET003_API_ORIGIN": values["CLOUD_RUN_ORIGIN"],
                "NET003_AI_USER_PRIVATE_KEY": values["GCP004_AI_USER_PRIVATE_KEY"],
                "NET003_PROVIDER_PRIVATE_KEY": values["GCP004_PROVIDER_PRIVATE_KEY"],
                "NET003_PROVIDER_ADDRESS": provider,
                "NET003_WORKER_PRIVATE_KEY": values["GCP004_WORKER_PRIVATE_KEY"],
                "NET003_WORKER_SIGNER_ADDRESS": worker,
                "BACKEND_PRIVATE_KEY": values["GCP004_EXECUTOR_PRIVATE_KEY"],
                "BACKEND_EXECUTOR_ADDRESS": executor,
                "CHAIN_ID": "421614",
                "USDC_SEPOLIA_ADDRESS": USDC,
                "STORAGE_ADAPTER": "s3",
                "OBJECT_STORAGE_REGION": "auto",
                "RUNNERS_ENABLED": "false",
            }
        )
        error_log = args.error_log or args.output.with_suffix(".stderr.log")
        stdout = run_smoke(env, error_log)
        evidence = json.loads(stdout)
        journeys = evidence.get("journeys", [])
        if evidence.get("status") != "passed" or len(journeys) != 2:
            raise RuntimeError("bounded live journey returned incomplete evidence")
        sanitized = {
            "status": "passed",
            "chain_id": evidence["chain_id"],
            "contract": evidence["contract"],
            "journeys": journeys,
        }
        if "execution" in evidence:
            sanitized["execution"] = evidence["execution"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        args.output.chmod(0o600)
        print(json.dumps(sanitized))
        return 0
    except (
        KeyError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as exc:
        print(f"GCP-004 storage exchange failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
