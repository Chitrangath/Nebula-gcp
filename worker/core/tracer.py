"""Inference trace for PoAE Step 2."""

import hashlib

import torch


def run_inference_with_trace(model, input_data, model_id: str):
    """Run inference and record checkpoint hashes."""
    from core.preprocessor import preprocess_input

    trace_hashes = []
    device = next(model.parameters()).device
    x = preprocess_input(input_data, model_id).to(device)

    try:
        layers = list(model.children())
    except Exception:
        with torch.no_grad():
            output = model(x)
        return output.cpu().numpy(), ["skipped_non_sequential"]

    if len(layers) == 0:
        with torch.no_grad():
            output = model(x)
        return output.cpu().numpy(), ["skipped_no_children"]

    checkpoint_indices = sorted(
        set(
            [
                0,
                len(layers) // 3,
                2 * len(layers) // 3,
                len(layers) - 1,
            ]
        )
    )

    with torch.no_grad():
        for i, layer in enumerate(layers):
            x = layer(x)
            if i in checkpoint_indices:
                tensor_bytes = x.detach().cpu().numpy().tobytes()
                h = hashlib.sha256(tensor_bytes).hexdigest()
                trace_hashes.append(h)

    final_output = x.detach().cpu().numpy()
    return final_output, trace_hashes
