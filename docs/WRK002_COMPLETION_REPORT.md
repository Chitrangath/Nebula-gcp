# WRK-002 Completion Report

## Outcome

The worker now provides an explicitly selected `ResNet50Executor` behind the
existing `execute(model_bytes, input_bytes, model_id)` seam while retaining the
`DeterministicFixtureExecutor` default for fast protocol and Phase 3 tests.
`EXECUTOR_ADAPTER=resnet50` activates the safe hash-keyed `ModelLoader` and the
real adapter; `EXECUTOR_DEVICE=cpu` is the safe default and GPU selection is
explicit.

The real adapter builds `torchvision.models.resnet50(weights=None)` in code and
strictly applies a verified safetensors state dictionary. It uses evaluation and
inference modes, fixed seeds, deterministic algorithms, cuDNN benchmarking off,
and TF32 off. It applies bounded PNG/JPEG decoding, EXIF orientation, RGB
conversion, bilinear short-side resize to 256, integer center crop to 224,
float32 CHW conversion, ImageNet normalization, and a batch dimension.

Canonical output is newline-terminated compact JSON with fixed field order,
index-ascending top-k tie breaking, and IEEE-754 hexadecimal probability
strings. The adapter emits exactly four hashes in this order:
`preprocess`, `forward`, `softmax`, `topk`. Tensor checkpoint serialization has
an explicit version, little-endian float32 dtype, shape header, and contiguous
bytes. The legacy dynamic tracer is not imported or called by this adapter.
Device out-of-memory, unsafe dimensions, decompression bombs, corrupt images,
invalid logits, wrong model IDs, and invalid state dictionaries map to bounded
failures without logging tensor contents.

The obsolete worker fingerprint implementation was replaced with the canonical
versioned ResNet50 fingerprint semantics. Golden tests prove backend/worker
fingerprint, ordered Merkle, and EIP-712 typed-data/signature convergence.

## Verification

- Worker loader/executor suite: 44 passed.
- Protocol convergence suite: 3 passed.
- Ten semantic CPU vectors freeze exact output and all four checkpoint hashes;
  ten additional genuine code-defined ResNet50 CPU vectors freeze output hashes
  from a safetensors artifact containing all 25,557,032 parameters.
- Restart-repeatability, tie behavior, fixture retention, corrupt/truncated
  images, dimension limits, invalid state/model, and synthetic OOM are covered.
- Ruff check and format passed for all changed worker modules/tests.
- The existing Phase 3 fixture executor remains the default, preventing this
  opt-in real adapter from changing established protocol behavior.

No target NVIDIA GPU, driver, CUDA configuration, real approved artifact, local
Anvil real-model settlement, or public Sepolia settlement was available or
authorized. Those acceptance gates require owner hardware/artifact coordinates
and deployment, so WRK-002 is explicitly PARTIAL rather than overstated.

## Skill usage

### Discovered

`solidity-foundry-security`, `tdd`, `domain-modeling`, `code-review`,
`diagnosing-bugs`, `research`, `codebase-design`, `grill-with-docs`,
`improve-codebase-architecture`, `handoff`, `ask-matt`,
`setup-matt-pocock-skills`, `teach`, and `wizard`.

### Applied

1. `tdd`: exact output/checkpoint behavior, unsafe inputs, resource failure,
   real state loading, and convergence were exercised at public seams.
2. `codebase-design`: the executor seam was retained, with fixture and ResNet50
   as its two concrete adapters; model acquisition remains behind ModelLoader.
3. `domain-modeling`: added canonical `Model artifact` and `Model adapter`
   vocabulary so immutable weights and executable rules are not conflated.
4. `code-review`: independent standards/spec review is run on the fixed commit.

### Not applied

`diagnosing-bugs` was unnecessary after bounded red-green iterations;
`solidity-foundry-security` did not apply because contracts were untouched;
`wizard` is deferred to owner-only GPU/public deployment gates. Research,
routing, teaching, handoff, and broad refactoring skills were outside scope.
