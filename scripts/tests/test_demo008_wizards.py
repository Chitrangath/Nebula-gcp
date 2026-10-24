"""Public CLI and safety contracts for DEMO-008 operator wizards."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = ROOT / "scripts/demo008_provider_worker_wizard.sh"
ACCEPTANCE = ROOT / "scripts/demo008_three_device_acceptance_wizard.sh"


def run(path: Path, option: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(path), option], cwd=ROOT, check=False, capture_output=True, text=True)


def test_provider_plan_is_gpu_worker_only_and_real_multimodel() -> None:
    result = run(PROVIDER, "--plan")
    assert result.returncode == 0, result.stderr
    assert "real ResNet50 and BERT" in result.stdout
    assert "provider-only" in result.stdout
    text = PROVIDER.read_text()
    assert "EXECUTOR_ADAPTER multimodel" in text
    assert "EXECUTOR_DEVICE cuda" in text
    assert "app.runners" not in text
    assert "DATABASE_URL" not in text
    assert "R2_SECRET_ACCESS_KEY" not in text


def test_acceptance_plan_orders_browser_jobs_recovery_and_evidence() -> None:
    result = run(ACCEPTANCE, "--plan")
    assert result.returncode == 0, result.stderr
    stages = [
        "reviewed deployment",
        "Device B and Device C",
        "ResNet50 browser journey",
        "provider interruption",
        "BERT browser journey",
        "sanitized acceptance evidence",
        "required browser screenshots",
        "stop all controlled processes",
    ]
    positions = [result.stdout.index(stage) for stage in stages]
    assert positions == sorted(positions)
    text = ACCEPTANCE.read_text()
    assert "DEMO008_ACCESS_TOKEN" in text
    assert "ask_secret" in text
    assert "demo008_acceptance_probe.py" in text
    assert "gcp006_laptop_demo_runtime_wizard.sh --stop" in text
