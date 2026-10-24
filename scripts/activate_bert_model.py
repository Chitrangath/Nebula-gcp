#!/usr/bin/env python3
"""Publish verified BERT weights privately and configure the existing model row.

Defaults to a local-only plan. Run with backend Python and --apply after upgrading
the database migration and deploying the multimodel worker/API code.
"""

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from prepare_bert_model import FILES, REVISION


async def activate(config_dir: Path, artifact_dir: Path) -> None:
    """Upload a hash-addressed object and update only the BERT registry entry."""
    import boto3
    from botocore.config import Config
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    def read(name: str) -> str:
        path = config_dir / name
        if path.stat().st_mode & 0o077:
            raise ValueError(f"insecure protected configuration: {name}")
        return path.read_text().strip()

    os.environ["DATABASE_URL"] = read("DATABASE_URL")
    os.environ["JWT_SECRET"] = read("JWT_SECRET")
    from app.models import SupportedModel

    digest = FILES["model.safetensors"][0]
    key = f"models/bert-base/{digest}.safetensors"
    prefix = read("OBJECT_STORAGE_PREFIX")
    object_key = f"{prefix}/{key}"
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{read('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=read("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=read("R2_SECRET_ACCESS_KEY"),
        config=Config(
            connect_timeout=10, read_timeout=120, retries={"max_attempts": 2}
        ),
    )
    bucket = read("R2_BUCKET_NAME")
    print("Publishing verified BERT weights to the private model prefix…", flush=True)
    await asyncio.to_thread(
        client.upload_file, str(artifact_dir / "model.safetensors"), bucket, object_key
    )
    response = await asyncio.to_thread(client.get_object, Bucket=bucket, Key=object_key)

    def verify_uploaded() -> None:
        try:
            uploaded_digest = hashlib.sha256()
            for chunk in response["Body"].iter_chunks(1024 * 1024):
                uploaded_digest.update(chunk)
            if uploaded_digest.hexdigest() != digest:
                raise ValueError("private artifact read-back SHA-256 mismatch")
        finally:
            response["Body"].close()

    await asyncio.to_thread(verify_uploaded)
    engine = create_async_engine(read("DATABASE_URL"))
    try:
        async with async_sessionmaker(engine)() as db, db.begin():
            resnet = await db.get(SupportedModel, "resnet50")
            if resnet is None:
                raise ValueError("configure ResNet50 and its fixed escrow price first")
            bert = (
                await db.execute(
                    select(SupportedModel)
                    .where(SupportedModel.id == "bert-base")
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if bert is None:
                bert = SupportedModel(id="bert-base")
                db.add(bert)
            bert.name = "BERT · Review sentiment (1–5 stars)"
            bert.framework = "pytorch-safetensors"
            bert.model_source_url = key
            bert.model_hash_sha256 = digest
            bert.model_version = REVISION
            bert.preprocessing_version = "bert-sentiment-v1"
            bert.vram_required_gb = 4
            bert.estimated_inference_ms = 3000
            bert.max_input_size_mb = (
                1  # Upload validation additionally caps BERT at 64 KiB.
            )
            bert.supported_formats = ["txt"]
            bert.input_type = "text"
            bert.price_base_units = resnet.price_base_units
    finally:
        await engine.dispose()
    print(
        "BERT artifact read-back verified and registry configured. No jobs or chain transactions submitted."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    for name, (digest, _) in FILES.items():
        with (args.artifact_dir / name).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise SystemExit(f"Unverified artifact: {name}")
    if args.apply:
        asyncio.run(activate(args.config_dir, args.artifact_dir))
    else:
        print(
            "Verified local artifacts. Plan: publish private hash-addressed BERT weights, verify read-back, configure bert-base with ResNet50's fixed escrow price. Pass --apply to execute."
        )


if __name__ == "__main__":
    main()
