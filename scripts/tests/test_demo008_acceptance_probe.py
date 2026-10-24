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
    attempt_history = [{"attempt_number": 1, "node_id": node, "status": "completed"}]
    if model == "bert-base":
        attempt_history = [
            {"attempt_number": 1, "node_id": "11111111-1111-4111-8111-111111111111", "status": "failed"},
            {"attempt_number": 2, "node_id": node, "status": "completed"},
        ]
    return {
        "id": f"00000000-0000-4000-8000-{byte * 12}",
        "chain_job_id": "0x" + byte * 64,
        "model_id": model,
        "status": "completed",
        "attempt_count": 2 if model == "bert-base" else 1,
        "attempt_history": attempt_history,
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


def run_probe(tmp_path: Path, jobs: dict[str, dict[str, object]], *, require_reassignment: bool = False) -> subprocess.CompletedProcess[str]:
    resnet = tmp_path / "resnet.json"; bert = tmp_path / "bert.json"
    resnet.write_text(json.dumps(jobs["resnet"])); bert.write_text(json.dumps(jobs["bert"]))
    command = [
            "python3", str(PROBE), "--resnet-json", str(resnet),
            "--bert-json", str(bert),
            "--device-b-node", "11111111-1111-4111-8111-111111111111",
            "--device-c-node", "22222222-2222-4222-8222-222222222222",
            "--source-commit", "a" * 40,
            "--output", str(tmp_path / "evidence.json"),
        ]
    if require_reassignment:
        command.append("--require-reassignment")
    return subprocess.run(command,
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


def test_probe_accepts_sequential_jobs_on_the_same_provider_node(tmp_path: Path) -> None:
    node = "11111111-1111-4111-8111-111111111111"
    result = run_probe(tmp_path, {"resnet": job("resnet50", node, "1"), "bert": job("bert-base", node, "2")})

    assert result.returncode == 0, result.stderr


def test_probe_requires_bert_retry_evidence(tmp_path: Path) -> None:
    resnet = job("resnet50", "11111111-1111-4111-8111-111111111111", "1")
    bert = job("bert-base", "22222222-2222-4222-8222-222222222222", "2")
    bert["attempt_count"] = 1

    result = run_probe(tmp_path, {"resnet": resnet, "bert": bert}, require_reassignment=True)

    assert result.returncode == 1
    assert "retry/reassignment" in result.stderr


def test_probe_rejects_distinct_but_undeclared_nodes(tmp_path: Path) -> None:
    resnet = job("resnet50", "33333333-3333-4333-8333-333333333333", "1")
    bert = job("bert-base", "44444444-4444-4444-8444-444444444444", "2")
    bert["attempt_history"] = [
        {"attempt_number": 1, "node_id": resnet["assigned_node_id"], "status": "failed"},
        {"attempt_number": 2, "node_id": bert["assigned_node_id"], "status": "completed"},
    ]

    result = run_probe(tmp_path, {"resnet": resnet, "bert": bert})

    assert result.returncode == 1
    assert "declared Device B/C" in result.stderr


def test_probe_rejects_attempt_history_swapped_from_final_assignment(tmp_path: Path) -> None:
    resnet = job("resnet50", "11111111-1111-4111-8111-111111111111", "1")
    bert = job("bert-base", "22222222-2222-4222-8222-222222222222", "2")
    bert["attempt_history"] = [
        {"attempt_number": 1, "node_id": bert["assigned_node_id"], "status": "failed"},
        {"attempt_number": 2, "node_id": resnet["assigned_node_id"], "status": "completed"},
    ]

    result = run_probe(tmp_path, {"resnet": resnet, "bert": bert})

    assert result.returncode == 1
    assert "final assigned node" in result.stderr
