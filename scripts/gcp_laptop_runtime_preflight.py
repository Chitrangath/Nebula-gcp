#!/usr/bin/env python3
"""Read-only owner-laptop connectivity checks for the supervised demo runtime."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
from pathlib import Path

import asyncpg
import boto3
import httpx
from web3 import Web3

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


class PreflightError(RuntimeError):
    """Raised when a required owner runtime dependency is unavailable."""


def read_value(config_dir: Path, name: str) -> str:
    path = config_dir / name
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise PreflightError(f"missing or insecure protected configuration: {name}")
    value = path.read_text(encoding="utf-8")
    if not value or "\n" in value or "\r" in value:
        raise PreflightError(f"invalid protected configuration: {name}")
    return value


async def check_api(origin: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        for endpoint in ("/live", "/ready"):
            response = await client.get(origin.rstrip("/") + endpoint)
            if response.status_code != 200:
                raise PreflightError(f"Cloud Run {endpoint} did not return 200")


async def check_database(database_url: str) -> None:
    connection = await asyncpg.connect(database_url, timeout=10)
    try:
        if await connection.fetchval("SELECT 1") != 1:
            raise PreflightError(
                "Supabase connectivity check returned an unexpected result"
            )
    finally:
        await connection.close()


def check_storage(config_dir: Path) -> None:
    account = read_value(config_dir, "R2_ACCOUNT_ID")
    bucket = read_value(config_dir, "R2_BUCKET_NAME")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=read_value(config_dir, "R2_ACCESS_KEY_ID"),
        aws_secret_access_key=read_value(config_dir, "R2_SECRET_ACCESS_KEY"),
    )
    client.head_bucket(Bucket=bucket)


def check_chain(config_dir: Path) -> None:
    rpc = read_value(config_dir, "ARBITRUM_SEPOLIA_RPC")
    contract = read_value(config_dir, "NEBULA_PAYMENT_CONTRACT")
    if not ADDRESS.fullmatch(contract):
        raise PreflightError("deployed contract address is invalid")
    web3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
    if not web3.is_connected() or web3.eth.chain_id != 421614:
        raise PreflightError("RPC is not connected to Arbitrum Sepolia")
    if not web3.eth.get_code(Web3.to_checksum_address(contract)):
        raise PreflightError("no deployed bytecode exists at the configured contract")


async def run(config_dir: Path) -> None:
    origin = read_value(config_dir, "CLOUD_RUN_ORIGIN")
    await check_api(origin)
    await check_database(read_value(config_dir, "DATABASE_URL"))
    await asyncio.to_thread(check_storage, config_dir)
    await asyncio.to_thread(check_chain, config_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.config_dir))
    except Exception as exc:  # noqa: BLE001 - external clients vary; never expose secret-bearing errors
        digest = hashlib.sha256(type(exc).__name__.encode()).hexdigest()[:12]
        raise SystemExit(
            f"runtime preflight failed safely ({type(exc).__name__}:{digest})"
        ) from None
    print("Cloud Run, Supabase, private R2, RPC, and deployed-contract checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
