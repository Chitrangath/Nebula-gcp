"""Offline, safetensors-only BERT sentiment inference with four PoAE checkpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import torch
from safetensors.torch import load as load_safetensors
from torch import nn
from transformers import BertConfig, BertForSequenceClassification, BertTokenizer

from core.resnet50_executor import canonical_tensor_bytes, configure_determinism

BERT_CHECKPOINTS = ["tokenize", "forward", "pool", "project"]
BERT_REVISION = "8f6f4e3a8f70be4b65d3a4a8762b6d781cda240d"
BERT_REPOSITORY = "nlptown/bert-base-multilingual-uncased-sentiment"
BERT_SHA256 = "0435c6c12c80a0a2206137c9fa8f6478fce4f4de88ac3d43d0f0e0da3c8c767b"
BERT_VOCAB_SHA256 = "87b44292b452f6c05afa49b2e488e7eedf79ea4f4c39db6f2f4b37764228ef3f"


def decode_text(data: bytes) -> str:
    """Validate a bounded UTF-8 review; preserve exact submitted text."""
    if not data or len(data) > 65536:
        raise ValueError("text must contain 1–65536 UTF-8 bytes")
    text = data.decode("utf-8", errors="strict")
    if not text.strip() or "\0" in text:
        raise ValueError("text must be nonempty and contain no NUL bytes")
    return text


class BertExecutor:
    """Execute the pinned multilingual BERT five-star sentiment classifier."""

    def __init__(
        self,
        *,
        device: str = "cpu",
        vocab_path: str | Path | None = None,
        tokenizer: Callable[..., Any] | None = None,
        model_factory: Callable[[], nn.Module] | None = None,
    ) -> None:
        self.device = torch.device(device)
        if tokenizer is None:
            path = Path(vocab_path) if vocab_path else None
            if (
                path is None
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != BERT_VOCAB_SHA256
            ):
                raise ValueError(
                    "BERT tokenizer missing or SHA-256 mismatch; run prepare_bert_model.py"
                )
            tokenizer = BertTokenizer(vocab_file=str(path), do_lower_case=True)
        self.tokenizer = tokenizer
        self.model_factory = model_factory or (
            lambda: BertForSequenceClassification(
                BertConfig(vocab_size=105879, num_labels=5, attn_implementation="eager")
            )
        )
        self._model: nn.Module | None = None
        self._artifact_hash: str | None = None

    def execute(
        self, model: bytes, input_data: bytes, model_id: str
    ) -> tuple[bytes, list[bytes]]:
        """Return canonical sentiment JSON and token/forward/pool/project hashes."""
        if model_id != "bert-base":
            raise ValueError("BERT adapter received an unapproved model ID")
        text = decode_text(input_data)
        configure_determinism()
        digest = hashlib.sha256(model).hexdigest()
        if self._artifact_hash != digest:
            network = self.model_factory()
            network.load_state_dict(load_safetensors(model), strict=True)
            self._model = network.eval().to(self.device)
            self._artifact_hash = digest
        encoded = self.tokenizer(text, return_tensors="pt", truncation=False)
        if encoded["input_ids"].shape[1] > 512:
            raise ValueError("BERT input exceeds 512 tokens; shorten the review")
        token_bytes = json.dumps(
            {key: value.tolist() for key, value in sorted(encoded.items())},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        with torch.inference_mode():
            assert self._model is not None
            hidden = self._model.bert(
                **{k: v.to(self.device) for k, v in encoded.items()}, return_dict=True
            )
            pooled = hidden.pooler_output
            logits = self._model.classifier(self._model.dropout(pooled))
            if logits.shape != (1, 5) or not torch.isfinite(logits).all():
                raise ValueError("BERT produced invalid classifier output")
            probabilities = torch.softmax(logits, dim=1)[0].cpu().tolist()
        scores = [
            {"stars": i + 1, "probability_hex": float(p).hex()}
            for i, p in enumerate(probabilities)
        ]
        stars = max(range(5), key=lambda i: (probabilities[i], -i)) + 1
        output = (
            json.dumps(
                {"model_id": model_id, "stars": stars, "scores": scores},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        trace = [
            token_bytes,
            canonical_tensor_bytes(hidden.last_hidden_state),
            canonical_tensor_bytes(pooled),
            output,
        ]
        return output, [hashlib.sha256(value).digest() for value in trace]
