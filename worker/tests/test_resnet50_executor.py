"""CPU behavior tests for deterministic ResNet50 execution semantics."""

import io

import pytest
import torch
from core.fixture_executor import CHECKPOINTS, DeterministicFixtureExecutor
from core.resnet50_executor import (
    MAX_IMAGE_DIMENSION,
    ModelExecutionError,
    ResNet50Executor,
    canonical_topk,
    preprocess_resnet50,
)
from PIL import Image
from safetensors.torch import save
from torch import Tensor, nn


class GoldenNetwork(nn.Module):
    """Small deterministic CPU oracle used to freeze adapter byte semantics."""

    def forward(self, value: Tensor) -> Tensor:
        scale = value[:, 0, 0, 0].reshape(1, 1)
        return scale * torch.arange(1000, dtype=torch.float32).reshape(1, 1000) / 1000


def image_bytes(
    color: tuple[int, int, int], *, size: tuple[int, int] = (300, 260)
) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def executor() -> ResNet50Executor:
    return ResNet50Executor(model_factory=GoldenNetwork, state_loader=lambda _value: {})


def test_fixture_executor_remains_available() -> None:
    output, hashes = DeterministicFixtureExecutor().execute(
        b"model", b"input", "resnet50"
    )
    assert output.endswith(b"\n")
    assert len(hashes) == len(CHECKPOINTS) == 4


@pytest.mark.parametrize(
    ("color", "output_sha256", "trace_hex"),
    [
        (
            (0, 0, 0),
            "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            (
                "e43ddfc036a28b55884e8a420bf50df5cb95f3eec7e8e70ac07d0e5b60734d18",
                "a48561ecf8b77f3f30de201679eada8b2ae65aac6f3e92982b6b32e27d2e0705",
                "a297a7c4c0267ae2eb04b20a944e9a8920b2b0d991d5bd7698e82fcc1223736f",
                "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            ),
        ),
        (
            (255, 255, 255),
            "085bd7ecc1f3a4b764e4fe40307b6c9acf518ebac9307af0e35152357b2d85e7",
            (
                "e4a887eeebdb8b6b48a307996db57ae3ba876eadc592857f942cc23b98cc6991",
                "6fe4fc7da3c0f5eed93656b2b0c392d6a40a9047432b8eaa93809f988ec06c36",
                "5392700451e17fe853ea19679e02edd212a51210ed8cfa532a59f2d443cc7bdf",
                "085bd7ecc1f3a4b764e4fe40307b6c9acf518ebac9307af0e35152357b2d85e7",
            ),
        ),
        (
            (255, 0, 0),
            "085bd7ecc1f3a4b764e4fe40307b6c9acf518ebac9307af0e35152357b2d85e7",
            (
                "9be4ad96ca362feb83fe8d180ef1034dacabf06a872c85cc95f77ff0dd666ff0",
                "6fe4fc7da3c0f5eed93656b2b0c392d6a40a9047432b8eaa93809f988ec06c36",
                "5392700451e17fe853ea19679e02edd212a51210ed8cfa532a59f2d443cc7bdf",
                "085bd7ecc1f3a4b764e4fe40307b6c9acf518ebac9307af0e35152357b2d85e7",
            ),
        ),
        (
            (0, 255, 0),
            "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            (
                "e4efdff64df7efb3d50a36e01c821b27ece13c97990ad549f2670d4769488129",
                "a48561ecf8b77f3f30de201679eada8b2ae65aac6f3e92982b6b32e27d2e0705",
                "a297a7c4c0267ae2eb04b20a944e9a8920b2b0d991d5bd7698e82fcc1223736f",
                "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            ),
        ),
        (
            (0, 0, 255),
            "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            (
                "8eb872ddae13f5767e5cf95e4fece7dcdd5e8843a7bcf4251f70a82eb5032a35",
                "a48561ecf8b77f3f30de201679eada8b2ae65aac6f3e92982b6b32e27d2e0705",
                "a297a7c4c0267ae2eb04b20a944e9a8920b2b0d991d5bd7698e82fcc1223736f",
                "e3ac0259084d91461e161abb0382953fde6f01250d69695815c4b76a44b3980e",
            ),
        ),
        (
            (10, 20, 30),
            "ca25db7b57e99f511ff2d8b1a043576446187b28380d94899f5073939446ff9e",
            (
                "fbe36432381a0074920dcc60e1437fd3890503928c7dd736b3782503509dc09f",
                "5bce6ec6c5fb2f75b5710ec5d0d055910900cca0f8d7a48f3d5ae895e7d06e6a",
                "9237e6f7048fbb161a18498972de142836fcf052f7b07931168e3996e2684925",
                "ca25db7b57e99f511ff2d8b1a043576446187b28380d94899f5073939446ff9e",
            ),
        ),
        (
            (40, 50, 60),
            "aa03506541ad3ca5682f0e15d4ed70e24ce14e33aef196f8ee8d8ff8eec5e05d",
            (
                "49b9e0057860f6f1111eaa778d87b253f2065081834468bd43ae3db011839692",
                "954f65881e10df395383b44bc534b4b1a644c3a07ad04e9c296eb7b63292d398",
                "3b4fd9ebd66cc186f23b0338c84dd908d40a7e57b3cf6db6c00ac1b52cd9b79d",
                "aa03506541ad3ca5682f0e15d4ed70e24ce14e33aef196f8ee8d8ff8eec5e05d",
            ),
        ),
        (
            (70, 80, 90),
            "0a409211426adb0851b9356d1baf45dd9aa319e6f5cab55c08eae7d2a589553b",
            (
                "d4df47f8c92a5a0d44f5299ca440c1af6043d63b3f4646ab064541b95206370a",
                "d0d255408720a092f8df2d132b9cb9daf2ee066263790f27b702f8916a462986",
                "095edc03fcf8dd7bb79d2bdfbbaa8ba8484561319efc67e103379a7840f234f9",
                "0a409211426adb0851b9356d1baf45dd9aa319e6f5cab55c08eae7d2a589553b",
            ),
        ),
        (
            (120, 130, 140),
            "6dcbe170fdea93a7e2d8107e595309d7fbbc91566d246948e7206eda1be63fc8",
            (
                "59d0b44450081c8944bcbe57072ad7cb3679dd68af96b38eba1a79fb1ce20749",
                "2e6d428a2b4b6400656eb038f184be3ea46b86e77e79a855185851839f16fbb0",
                "03a060d06886574c56754e2b04a75b864e925f634618f8b33c42212f8ace572e",
                "6dcbe170fdea93a7e2d8107e595309d7fbbc91566d246948e7206eda1be63fc8",
            ),
        ),
        (
            (200, 150, 100),
            "804eddb08101b3604f79d7d1db204a362b61ca46fc8c357ea2baa79ca2d58b95",
            (
                "dc105c7667c7cb6a1ab3ad668985801eb3dfb4e8248c8cf637d92e2b05aa1e5b",
                "9530c4db2d797c2af5f8c5b1934dbefebad7987212b10c1953807e6ea804046c",
                "ddfbe3fd19c052631b6a96517fa882719dad6504de0fe303713f2d435d3bc405",
                "804eddb08101b3604f79d7d1db204a362b61ca46fc8c357ea2baa79ca2d58b95",
            ),
        ),
    ],
)
def test_ten_cpu_golden_vectors(
    color: tuple[int, int, int], output_sha256: str, trace_hex: tuple[str, ...]
) -> None:
    import hashlib

    output, trace = executor().execute(
        b"approved-safetensors", image_bytes(color), "resnet50"
    )
    assert hashlib.sha256(output).hexdigest() == output_sha256
    assert tuple(value.hex() for value in trace) == trace_hex


def test_restart_repeatability() -> None:
    args = (b"approved-safetensors", image_bytes((12, 34, 56)), "resnet50")
    assert executor().execute(*args) == executor().execute(*args)


def test_canonical_topk_uses_index_ascending_tie_break_and_newline() -> None:
    probabilities = torch.zeros((1, 1000), dtype=torch.float32)
    probabilities[0, 7] = probabilities[0, 3] = 0.5
    assert canonical_topk(probabilities).startswith(
        b'{"model_id":"resnet50","top_k":[{"index":3,"probability_hex":"0x1.0000000000000p-1"}'
    )
    assert canonical_topk(probabilities).endswith(b"\n")


@pytest.mark.parametrize("payload", [b"", b"not-image", image_bytes((1, 2, 3))[:20]])
def test_corrupt_or_truncated_inputs_fail_safely(payload: bytes) -> None:
    with pytest.raises(ModelExecutionError):
        preprocess_resnet50(payload)


def test_malformed_png_chunk_is_reported_as_safe_input_failure() -> None:
    # The original live smoke image has a broken chunk, despite a valid PNG header.
    payload = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
    )
    with pytest.raises(ModelExecutionError, match="corrupt, truncated, or unsafe"):
        preprocess_resnet50(payload)


def test_decoded_dimension_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.resnet50_executor.MAX_IMAGE_DIMENSION", 10)
    with pytest.raises(ModelExecutionError, match="dimensions"):
        preprocess_resnet50(image_bytes((1, 2, 3), size=(11, 11)))
    assert MAX_IMAGE_DIMENSION > 10


def test_invalid_model_id_and_state_dictionary_are_rejected() -> None:
    with pytest.raises(ModelExecutionError, match="model ID"):
        executor().execute(b"weights", image_bytes((1, 2, 3)), "yolov5")
    failing = ResNet50Executor(
        model_factory=GoldenNetwork,
        state_loader=lambda _value: (_ for _ in ()).throw(ValueError()),
    )
    with pytest.raises(ModelExecutionError, match="state dictionary"):
        failing.execute(b"bad", image_bytes((1, 2, 3)), "resnet50")


def test_out_of_memory_is_mapped_to_safe_failure() -> None:
    class OutOfMemory(nn.Module):
        def forward(self, _value: Tensor) -> Tensor:
            raise torch.OutOfMemoryError("synthetic")

    failing = ResNet50Executor(
        model_factory=OutOfMemory, state_loader=lambda _value: {}
    )
    with pytest.raises(ModelExecutionError, match="device memory"):
        failing.execute(b"weights", image_bytes((1, 2, 3)), "resnet50")


def test_real_factory_is_code_defined_resnet50() -> None:
    network = ResNet50Executor().model_factory()
    assert network.__class__.__name__ == "ResNet"
    assert sum(parameter.numel() for parameter in network.parameters()) == 25_557_032


@pytest.fixture(scope="module")
def real_resnet_runtime() -> tuple[bytes, ResNet50Executor]:
    torch.manual_seed(0)
    source = ResNet50Executor().model_factory()
    return save(source.state_dict()), ResNet50Executor(device="cpu")


@pytest.mark.parametrize(
    ("color", "expected_output_hash"),
    [
        ((0, 0, 0), "e0392935ed95f98d180f7a265f7cdcdaecb461a23f91e78b8c59797c4dcd333e"),
        (
            (255, 255, 255),
            "4f90dffc20a66fad503977e39d7588caabf71f234180c353f14210a6069d6603",
        ),
        (
            (255, 0, 0),
            "e80edeabddda5a4661bdbf08e31d662a5c2d369e6ddbbe48ff7cb15f9e556810",
        ),
        (
            (0, 255, 0),
            "eefb526e70d8e616e88b58cf1754c4a9db0380cc82efd4dd365b3fc28dea8de7",
        ),
        (
            (0, 0, 255),
            "f8e6b9fa27500cd2a0b156ac0ad82007a842960cff84f01c44f0c714ffc5d43c",
        ),
        (
            (10, 20, 30),
            "1aa6600fde4b0ed85cba2c3148ae1b2b9ff6dc5a50282da976a9a85a09ff558a",
        ),
        (
            (40, 50, 60),
            "264cf9c9dfb5215d0dcba461d08e3ffacf201dd6f516d87ea6745138b85b3d8a",
        ),
        (
            (70, 80, 90),
            "5b46cd2371939375bfdb33f6955034bd5e0b497f63d4a3b4a7c1baf2ae613b9d",
        ),
        (
            (120, 130, 140),
            "b4b4eb3e5587f57151f6fe058043816a8e466586afd226858bc40a66689b910f",
        ),
        (
            (200, 150, 100),
            "be638a0279616060fdc105237e9b692a41699b5b3bc8bfec0147a0c1be8bb38b",
        ),
    ],
)
def test_ten_real_resnet50_cpu_golden_vectors(
    real_resnet_runtime: tuple[bytes, ResNet50Executor],
    color: tuple[int, int, int],
    expected_output_hash: str,
) -> None:
    import hashlib

    artifact, adapter = real_resnet_runtime
    output, trace = adapter.execute(artifact, image_bytes(color), "resnet50")
    assert hashlib.sha256(output).hexdigest() == expected_output_hash
    assert len(trace) == 4


def test_real_resnet50_safetensors_cpu_execution_repeats(
    real_resnet_runtime: tuple[bytes, ResNet50Executor],
) -> None:
    artifact, adapter = real_resnet_runtime
    first = adapter.execute(artifact, image_bytes((12, 34, 56)), "resnet50")
    second = adapter.execute(artifact, image_bytes((12, 34, 56)), "resnet50")
    assert first == second
    assert len(first[1]) == 4


@pytest.mark.parametrize("mode", ["L", "RGBA"])
def test_rgb_conversion_layout_dtype_and_batch_are_fixed(mode: str) -> None:
    output = io.BytesIO()
    Image.new(mode, (301, 259), 128).save(output, format="PNG")
    tensor = preprocess_resnet50(output.getvalue())
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == torch.float32


def test_deterministic_backend_flags_are_applied() -> None:
    executor().execute(b"weights", image_bytes((1, 2, 3)), "resnet50")
    assert torch.are_deterministic_algorithms_enabled()
    assert not torch.backends.cudnn.benchmark
    assert torch.backends.cudnn.deterministic
    assert not torch.backends.cuda.matmul.allow_tf32
    assert not torch.backends.cudnn.allow_tf32
