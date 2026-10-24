"""Dispatch approved model IDs to code-defined inference adapters."""

from core.fixture_executor import Executor
from core.resnet50_executor import ResNet50Executor


class MultiModelExecutor:
    """Keep one resident model adapter so two models fit small provider GPUs."""

    def __init__(self, *, device: str = "cpu", vocab_path: str | None = None) -> None:
        from core.bert_executor import BertExecutor

        # Fail before heartbeat advertisement if the offline tokenizer is absent
        # or corrupt, rather than accepting a funded job we cannot execute.
        BertExecutor(device=device, vocab_path=vocab_path)
        if device.startswith("cuda"):
            import torch

            from core.resnet50_executor import configure_determinism

            configure_determinism()
            try:
                sample = torch.ones((4, 4), device=device)
                torch.mm(sample, sample)
                torch.cuda.synchronize()
            except RuntimeError as exc:
                raise RuntimeError(
                    "GPU runtime unsupported: install the matching worker requirements profile before starting"
                ) from exc
        self.device = device
        self.vocab_path = vocab_path
        self._adapter: Executor | None = None
        self._model_id: str | None = None

    def execute(
        self, model: bytes, input_data: bytes, model_id: str
    ) -> tuple[bytes, list[bytes]]:
        """Run only an explicitly supported model; never silently use fixtures."""
        if model_id not in {"resnet50", "bert-base"}:
            raise ValueError("unapproved model ID")
        if self._model_id != model_id:
            self._adapter = None
            if self.device == "cuda":
                import torch

                torch.cuda.empty_cache()
            if model_id == "resnet50":
                self._adapter = ResNet50Executor(device=self.device)
            else:
                from core.bert_executor import BertExecutor

                self._adapter = BertExecutor(
                    device=self.device, vocab_path=self.vocab_path
                )
            self._model_id = model_id
        assert self._adapter is not None
        return self._adapter.execute(model, input_data, model_id)
