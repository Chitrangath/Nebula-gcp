#!/usr/bin/env python3
"""Validate and record sanitized DEMO-008 two-job acceptance evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class AcceptanceError(ValueError):
    """A live job does not satisfy the public demonstration contract."""


def read_job(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceError("job response must be a JSON object")
    return value


def fetch_job(origin: str, job_id: str, token: str) -> dict[str, Any]:
    if not origin.startswith("https://") or "@" in origin:
        raise AcceptanceError("API origin must be credential-free HTTPS")
    request = urllib.request.Request(
        f"{origin.rstrip('/')}/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.load(response)
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"job retrieval failed ({type(exc).__name__})") from None
    if not isinstance(value, dict):
        raise AcceptanceError("job response must be a JSON object")
    return value


def validate_job(job: dict[str, Any], expected_model: str) -> dict[str, Any]:
    if job.get("model_id") != expected_model:
        raise AcceptanceError(f"expected {expected_model} job")
    expected = {
        "status": "completed",
        "chain_id": 421614,
        "on_chain_state": "Settled",
        "proof_verification_status": "valid",
        "provider_payment_credit_status": "credited",
        "reconciliation_health": "match",
        "result_available": True,
    }
    for name, value in expected.items():
        if job.get(name) != value:
            raise AcceptanceError(f"{expected_model} {name} is not {value!r}")
    attempt_count = job.get("attempt_count")
    if not isinstance(attempt_count, int) or attempt_count < 1:
        raise AcceptanceError(f"{expected_model} has no completed attempt")
    if expected_model == "bert-base" and attempt_count < 2:
        raise AcceptanceError("BERT has no retry/reassignment evidence")
    node_id = job.get("assigned_node_id")
    try:
        uuid.UUID(str(node_id))
    except ValueError:
        raise AcceptanceError(f"{expected_model} has no valid assigned node")
    fingerprint = job.get("fingerprint")
    if fingerprint != job.get("proof_fingerprint") or not isinstance(fingerprint, str):
        raise AcceptanceError(f"{expected_model} proof fingerprint does not match")
    transactions: dict[str, str] = {}
    for name in ("escrow", "assignment", "proof", "settlement"):
        evidence = job.get(f"{name}_transaction")
        if not isinstance(evidence, dict) or evidence.get("status") not in {"confirmed", "finalized"}:
            raise AcceptanceError(f"{expected_model} {name} transaction is not confirmed")
        tx_hash = evidence.get("hash")
        if not isinstance(tx_hash, str) or TX_HASH.fullmatch(tx_hash) is None:
            raise AcceptanceError(f"{expected_model} {name} transaction hash is invalid")
        transactions[name] = tx_hash
    return {
        "job_id": job.get("id"),
        "chain_job_id": job.get("chain_job_id"),
        "model_id": expected_model,
        "assigned_node_id": node_id,
        "fingerprint": fingerprint,
        "attempt_count": attempt_count,
        "transactions": transactions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api-origin")
    source.add_argument("--resnet-json", type=Path)
    parser.add_argument("--bert-json", type=Path)
    parser.add_argument("--resnet-job")
    parser.add_argument("--bert-job")
    parser.add_argument("--device-b-node", required=True)
    parser.add_argument("--device-c-node", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        declared_nodes = {args.device_b_node.lower(), args.device_c_node.lower()}
        if len(declared_nodes) != 2:
            raise AcceptanceError("Device B and Device C node IDs must differ")
        for node_id in declared_nodes:
            try:
                uuid.UUID(node_id)
            except ValueError:
                raise AcceptanceError("declared Device B/C node ID is invalid") from None
        if COMMIT.fullmatch(args.source_commit) is None:
            raise AcceptanceError("source commit must be a full lowercase Git SHA")
        if args.api_origin:
            if not args.resnet_job or not args.bert_job:
                raise AcceptanceError("live mode requires both job IDs")
            token = os.environ.get("DEMO008_ACCESS_TOKEN", "")
            if not token:
                raise AcceptanceError("DEMO008_ACCESS_TOKEN is required in live mode")
            resnet_job = fetch_job(args.api_origin, args.resnet_job, token)
            bert_job = fetch_job(args.api_origin, args.bert_job, token)
        else:
            if args.bert_json is None:
                raise AcceptanceError("fixture mode requires --bert-json")
            resnet_job = read_job(args.resnet_json)
            bert_job = read_job(args.bert_json)
        journeys = [validate_job(resnet_job, "resnet50"), validate_job(bert_job, "bert-base")]
        if journeys[0]["assigned_node_id"] == journeys[1]["assigned_node_id"]:
            raise AcceptanceError("the two jobs must settle on distinct GPU nodes")
        if {str(value["assigned_node_id"]).lower() for value in journeys} != declared_nodes:
            raise AcceptanceError("settled jobs do not match the declared Device B/C nodes")
        bert_history = bert_job.get("attempt_history")
        if not isinstance(bert_history, list):
            raise AcceptanceError("BERT has no retry/reassignment history")
        sanitized_history = [
            {
                "attempt_number": item.get("attempt_number"),
                "node_id": item.get("node_id"),
                "status": item.get("status"),
            }
            for item in bert_history
            if isinstance(item, dict)
        ]
        if len(sanitized_history) < 2 or sanitized_history[-2].get("status") not in {"failed", "expired"} or sanitized_history[-1].get("status") != "completed":
            raise AcceptanceError("BERT has no failed-to-completed retry/reassignment history")
        history_nodes = {str(item.get("node_id", "")).lower() for item in sanitized_history[-2:]}
        if history_nodes != declared_nodes:
            raise AcceptanceError("BERT retry/reassignment did not cross the declared Device B/C nodes")
        journeys[1]["attempt_history"] = sanitized_history
        evidence = {"status": "passed", "source_commit": args.source_commit, "chain_id": 421614, "declared_nodes": sorted(declared_nodes), "journeys": journeys}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        os.chmod(args.output, 0o600)
    except (OSError, json.JSONDecodeError, AcceptanceError) as exc:
        print(f"DEMO-008 acceptance failed: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "evidence": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
