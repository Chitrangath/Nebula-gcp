#!/usr/bin/env python3
"""Download the pinned BERT release and independently verify both file hashes."""

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

REPOSITORY = "nlptown/bert-base-multilingual-uncased-sentiment"
REVISION = "8f6f4e3a8f70be4b65d3a4a8762b6d781cda240d"
FILES = {
    "model.safetensors": (
        "0435c6c12c80a0a2206137c9fa8f6478fce4f4de88ac3d43d0f0e0da3c8c767b",
        669464588,
    ),
    "vocab.txt": (
        "87b44292b452f6c05afa49b2e488e7eedf79ea4f4c39db6f2f4b37764228ef3f",
        2 * 1024 * 1024,
    ),
}


def acquire(directory: Path, filename: str, expected: str, limit: int) -> None:
    """Acquire one bounded file atomically, accepting only its pinned SHA-256."""
    destination = directory / filename
    if destination.exists():
        with destination.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() == expected:
                print(f"Verified cached {filename}", flush=True)
                return
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{filename}"
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=f".{filename}-")
    try:
        print(f"Downloading pinned {filename}…", flush=True)
        digest = hashlib.sha256()
        total = 0
        with (
            os.fdopen(descriptor, "wb") as output,
            urllib.request.urlopen(url, timeout=90) as response,
        ):
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ValueError("artifact exceeds approved byte bound")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch for {filename}")
        os.replace(temporary, destination)
        print(f"Verified {filename}: {total} bytes", flush=True)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, (digest, limit) in FILES.items():
        acquire(args.output_dir, filename, digest, limit)
    manifest = {
        "model_id": "bert-base",
        "repository": REPOSITORY,
        "revision": REVISION,
        "model_version": REVISION,
        "preprocessing_version": "bert-sentiment-v1",
        "files": {name: value[0] for name, value in FILES.items()},
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        "Set BERT_VOCAB_PATH to the verified vocab.txt path; use EXECUTOR_ADAPTER=multimodel."
    )


if __name__ == "__main__":
    main()
