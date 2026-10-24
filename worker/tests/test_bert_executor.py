"""BERT adapter behavior with a small real Transformer, without network calls."""

import json

import pytest
import torch
from safetensors.torch import save
from transformers import BertConfig, BertForSequenceClassification

from core.bert_executor import BertExecutor, decode_text


def test_multimodel_start_rejects_missing_or_corrupt_offline_tokenizer(tmp_path):
    from core.multimodel_executor import MultiModelExecutor

    with pytest.raises(ValueError, match="tokenizer"):
        MultiModelExecutor(vocab_path=tmp_path / "missing.txt")
    corrupt = tmp_path / "vocab.txt"
    corrupt.write_text("not the pinned vocabulary")
    with pytest.raises(ValueError, match="tokenizer"):
        MultiModelExecutor(vocab_path=corrupt)


def test_text_validation_rejects_empty_binary_and_oversize_inputs():
    for value in (b"", b" \n", b"\xff", b"hello\0world", b"a" * 65537):
        with pytest.raises(ValueError):
            decode_text(value)
    assert decode_text("Excellent café!".encode()) == "Excellent café!"


def test_real_transformer_produces_repeatable_sentiment_and_four_checkpoints():
    config = BertConfig(
        vocab_size=16,
        hidden_size=12,
        num_hidden_layers=1,
        num_attention_heads=3,
        intermediate_size=24,
        num_labels=5,
    )
    torch.manual_seed(42)
    network = BertForSequenceClassification(config)
    weights = save(network.state_dict())

    class Tokenizer:
        def __call__(self, text, **kwargs):
            return {
                "input_ids": torch.tensor([[2, 5, 3]]),
                "attention_mask": torch.ones((1, 3), dtype=torch.long),
                "token_type_ids": torch.zeros((1, 3), dtype=torch.long),
            }

    executor = BertExecutor(
        tokenizer=Tokenizer(),
        model_factory=lambda: BertForSequenceClassification(config),
    )
    first = executor.execute(weights, b"Excellent product", "bert-base")
    assert first == executor.execute(weights, b"Excellent product", "bert-base")
    result = json.loads(first[0])
    assert result["model_id"] == "bert-base"
    assert 1 <= result["stars"] <= 5
    assert len(result["scores"]) == 5
    assert len(first[1]) == 4 and all(len(item) == 32 for item in first[1])
    with pytest.raises(ValueError):
        executor.execute(weights, b"test", "resnet50")
