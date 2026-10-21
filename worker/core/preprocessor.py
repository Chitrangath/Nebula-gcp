"""Model-specific input preprocessing."""

import io

import torch


def preprocess_input(input_data: bytes, model_id: str) -> torch.Tensor:
    """Preprocess input based on model type."""
    if model_id in ["yolov5", "resnet50"]:
        return _preprocess_image(input_data)
    elif model_id == "bert-base":
        return _tokenize_text(input_data)
    elif model_id == "whisper-tiny":
        return _preprocess_audio(input_data)
    else:
        return torch.tensor(input_data)


def _preprocess_image(image_bytes: bytes) -> torch.Tensor:
    """Preprocess image for YOLO/ResNet."""
    import torchvision.transforms as transforms
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    return transform(img).unsqueeze(0)


def _tokenize_text(text_bytes: bytes) -> torch.Tensor:
    """Tokenize text for BERT."""
    from transformers import BertTokenizer

    text = text_bytes.decode("utf-8").strip()
    tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    return inputs["input_ids"]


def _preprocess_audio(audio_bytes: bytes) -> torch.Tensor:
    """Preprocess audio for Whisper."""
    import numpy as np

    audio = np.frombuffer(audio_bytes, dtype=np.float32)
    return torch.tensor(audio[:16000]).unsqueeze(0)
