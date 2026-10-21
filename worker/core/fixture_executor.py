"""Deterministic local executor behind the Phase 5 replacement seam."""

import hashlib
import json
from typing import Protocol

CHECKPOINTS = ["preprocess", "forward", "softmax", "topk"]


class Executor(Protocol):
    def execute(
        self, model: bytes, input_data: bytes, model_id: str
    ) -> tuple[bytes, list[bytes]]: ...


class DeterministicFixtureExecutor:
    def execute(
        self, model: bytes, input_data: bytes, model_id: str
    ) -> tuple[bytes, list[bytes]]:
        seed = hashlib.sha256(
            model + b"\0" + input_data + b"\0" + model_id.encode()
        ).digest()
        output = (
            json.dumps(
                {"digest": seed.hex(), "fixture": "nebula-v1"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        return output, [
            hashlib.sha256(name.encode() + b"\0" + seed).digest()
            for name in CHECKPOINTS
        ]
