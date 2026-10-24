"""Public CLI contract for DEMO-008 two-job acceptance evidence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/demo008_acceptance_probe.py"


def job(model: str, node: str, byte: str) -> dict[str, object]:
    def transaction(suffix: str) -> dict[str, object]:
        return {
            "hash": "0x" + suffix * 64,
            "status": "confirmed",
            "chain_id": 421614,
            "block_number": 322000000,
        }
    return {
        "id": f"00000000-0000-4000-8000-{byte * 12}",
        "chain_job_id": "0x" + byte * 64,
        "model_id": model,
        "status": "completed",
        "attempt_count": 2 if model == "bert-base" else 1,
        "chain_id": 421614,
        "on_chain_state": "Settled",
        "proof_verification_status": "valid",
        "provider_payment_credit_status": "credited",
        "reconciliation_health": "match",
        "result_available": True,
        "assigned_node_id": node,
        "fingerprint": "0x" + "a" * 64,
        "proof_fingerprint": "0x" + "a" * 64,
        "escrow_transaction": transaction("1"),
        "assignment_transaction": transaction("2"),
        "proof_transaction": transaction("3"),
        "settlement_transaction": transaction("4"),
    }


def run_probe(tmp_path: Path, jobs: dict[str, dict[str, object]]) -> subprocess.CompletedProcess[str]:
    resnet = tmp_path / "resnet.json"; bert = tmp_path / "bert.json"
    resnet.write_text(json.dumps(jobs["resnet"])); bert.write_text(json.dumps(jobs["bert"]))
    return subprocess.run(
        [
            "python3", str(PROBE), "--resnet-json", str(resnet),
            "--bert-json", str(bert), "--output", str(tmp_path / "evidence.json"),
        ],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )


def test_probe_accepts_two_settled_models_on_distinct_nodes_without_recording_token(tmp_path: Path) -> None:
    result = run_probe(tmp_path, {
        "resnet": job("resnet50", "11111111-1111-4111-8111-111111111111", "1"),
        "bert": job("bert-base", "22222222-2222-4222-8222-222222222222", "2"),
    })

    assert result.returncode == 0, result.stderr
    evidence = (tmp_path / "evidence.json").read_text()
    assert '"status": "passed"' in evidence
    assert "Authorization" not in evidence + result.stdout + result.stderr


def test_probe_rejects_jobs_assigned_to_the_same_provider_node(tmp_path: Path) -> None:
    node = "11111111-1111-4111-8111-111111111111"
    result = run_probe(tmp_path, {"resnet": job("resnet50", node, "1"), "bert": job("bert-base", node, "2")})

    assert result.returncode == 1
    assert "distinct GPU nodes" in result.stderr


def test_probe_requires_bert_retry_evidence(tmp_path: Path) -> None:
    resnet = job("resnet50", "11111111-1111-4111-8111-111111111111", "1")
    bert = job("bert-base", "22222222-2222-4222-8222-222222222222", "2")
    bert["attempt_count"] = 1

    result = run_probe(tmp_path, {"resnet": resnet, "bert": bert})

    assert result.returncode == 1
    assert "retry/reassignment" in result.stderr
