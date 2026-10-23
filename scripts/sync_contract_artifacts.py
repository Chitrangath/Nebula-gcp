#!/usr/bin/env python3
"""Build and deterministically synchronize the backend contract artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
FOUNDRY_ARTIFACT = CONTRACTS / "out/NebulaVerifiableAI.sol/NebulaVerifiableAI.json"
BACKEND_ABI = ROOT / "backend/app/nebula_abi.json"
BACKEND_METADATA = ROOT / "backend/app/nebula_artifact.json"
FRONTEND_ARTIFACT = ROOT / "frontend/src/contracts/nebula.json"

REQUIRED_FUNCTIONS = {
    "createJob(bytes32,bytes32)",
    "assignProvider(bytes32,address,bytes32,uint64)",
    "submitProof(bytes32,bytes32,bytes32,bytes32)",
    "verifyJob(bytes32,bool)",
    "requestTimeoutRefund(bytes32)",
    "withdraw()",
    "getJob(bytes32)",
    "getPendingWithdrawal(address)",
}


def _keccak_hex(value: str) -> str:
    from Crypto.Hash import keccak

    digest = keccak.new(digest_bits=256)
    digest.update(value.encode())
    return "0x" + digest.hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def generate(*, build: bool = True) -> tuple[str, str]:
    if build:
        subprocess.run(["forge", "build"], cwd=CONTRACTS, check=True)
    artifact = json.loads(FOUNDRY_ARTIFACT.read_text())
    abi = artifact["abi"]
    method_identifiers = artifact["methodIdentifiers"]
    missing = REQUIRED_FUNCTIONS - method_identifiers.keys()
    if missing:
        raise RuntimeError(f"Foundry artifact is missing canonical functions: {sorted(missing)}")

    functions = {
        signature: "0x" + method_identifiers[signature]
        for signature in sorted(REQUIRED_FUNCTIONS)
    }
    events = {}
    for item in abi:
        if item.get("type") == "event":
            signature = f"{item['name']}({','.join(i['type'] for i in item['inputs'])})"
            events[signature] = _keccak_hex(signature)

    abi_compact = json.dumps(abi, sort_keys=True, separators=(",", ":"))
    runtime = artifact["deployedBytecode"]["object"].removeprefix("0x")
    metadata = artifact["metadata"]
    manifest = {
        "abi_sha256": hashlib.sha256(abi_compact.encode()).hexdigest(),
        "runtime_bytecode_sha256": hashlib.sha256(bytes.fromhex(runtime)).hexdigest(),
        "compiler": metadata["compiler"],
        "settings": metadata["settings"],
        "function_selectors": functions,
        "event_signatures": dict(sorted(events.items())),
        "job_state": {
            "None": 0,
            "Created": 1,
            "Assigned": 2,
            "ProofSubmitted": 3,
            "Settled": 4,
            "Refunded": 5,
        },
    }
    return _canonical_json(abi), _canonical_json(manifest)


def generate_frontend(abi_text: str, metadata_text: str) -> str:
    """Build the browser artifact from reviewed canonical backend artifacts."""
    return _canonical_json({"abi": json.loads(abi_text), "metadata": json.loads(metadata_text)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail instead of updating stale files")
    parser.add_argument("--no-build", action="store_true", help="use the existing Foundry artifact")
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="synchronize the browser artifact from reviewed backend artifacts",
    )
    args = parser.parse_args()
    if args.frontend_only:
        frontend_text = generate_frontend(BACKEND_ABI.read_text(), BACKEND_METADATA.read_text())
        if FRONTEND_ARTIFACT.exists() and FRONTEND_ARTIFACT.read_text() == frontend_text:
            print("checked canonical frontend contract artifact")
            return 0
        if args.check:
            print(f"stale contract artifact: {FRONTEND_ARTIFACT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        FRONTEND_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        FRONTEND_ARTIFACT.write_text(frontend_text)
        print("synchronized canonical frontend contract artifact")
        return 0

    abi_text, metadata_text = generate(build=not args.no_build)
    frontend_text = generate_frontend(abi_text, metadata_text)
    stale = []
    for path, expected in (
        (BACKEND_ABI, abi_text),
        (BACKEND_METADATA, metadata_text),
        (FRONTEND_ARTIFACT, frontend_text),
    ):
        if not path.exists() or path.read_text() != expected:
            stale.append(path)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(expected)
    if stale and args.check:
        print("stale contract artifacts: " + ", ".join(str(p.relative_to(ROOT)) for p in stale), file=sys.stderr)
        return 1
    print(("checked" if args.check else "synchronized") + " canonical contract artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
