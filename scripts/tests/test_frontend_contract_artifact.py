"""FE-001 canonical frontend contract artifact tests."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_contract_artifacts.py"
SPEC = importlib.util.spec_from_file_location("sync_contract_artifacts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_frontend_artifact_is_generated_from_reviewed_backend_artifacts() -> None:
    abi_text = (ROOT / "backend/app/nebula_abi.json").read_text()
    metadata_text = (ROOT / "backend/app/nebula_artifact.json").read_text()
    frontend_text = MODULE.generate_frontend(abi_text, metadata_text)
    frontend = json.loads(frontend_text)

    assert frontend["abi"] == json.loads(abi_text)
    assert frontend["metadata"] == json.loads(metadata_text)
    assert (ROOT / "frontend/src/contracts/nebula.json").read_text() == frontend_text
