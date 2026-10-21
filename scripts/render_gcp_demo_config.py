#!/usr/bin/env python3
"""Render owner-approved GCP/Vercel configuration outside the Git worktree."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TEMPLATE = ROOT / "deploy/gcp-demo/cloud-run-service.template.yaml"
REWRITE_TEMPLATE = ROOT / "deploy/gcp-demo/vercel-rewrite.template.json"
PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")

SERVICE_VALUES = {
    "__OWNER_APPROVED_SERVICE_NAME__": "CLOUD_RUN_SERVICE",
    "__OWNER_APPROVED_RUNTIME_SERVICE_ACCOUNT__": "RUNTIME_SERVICE_ACCOUNT",
    "__OWNER_APPROVED_IMAGE_DIGEST__": "IMAGE_DIGEST",
    "__REAL_VERCEL_HTTPS_ORIGIN_REQUIRED__": "FRONTEND_URL",
    "__OWNER_APPROVED_DATABASE_URL_SECRET_VERSION__": "DATABASE_SECRET_VERSION",
    "__OWNER_APPROVED_JWT_SECRET_VERSION__": "JWT_SECRET_VERSION",
    "__OWNER_APPROVED_RPC_SECRET_VERSION__": "RPC_SECRET_VERSION",
    "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET_VERSION__": "R2_ACCESS_KEY_SECRET_VERSION",
    "__OWNER_APPROVED_R2_SECRET_KEY_SECRET_VERSION__": "R2_SECRET_KEY_SECRET_VERSION",
    "__OWNER_APPROVED_CONTRACT_ADDRESS__": "NEBULA_PAYMENT_CONTRACT",
    "__OWNER_APPROVED_CONTRACT_DEPLOYMENT_BLOCK__": "CONTRACT_DEPLOYMENT_BLOCK",
    "__OWNER_APPROVED_CONTRACT_OWNER_ADDRESS__": "CONTRACT_OWNER_ADDRESS",
    "__OWNER_APPROVED_CONTRACT_VERIFIER_ADDRESS__": "CONTRACT_VERIFIER_ADDRESS",
    "__OWNER_APPROVED_R2_ACCOUNT_ID__": "R2_ACCOUNT_ID",
    "__OWNER_APPROVED_R2_BUCKET_NAME__": "R2_BUCKET_NAME",
    "__OWNER_APPROVED_STORAGE_PREFIX__": "OBJECT_STORAGE_PREFIX",
}
FIXED_VALUES = {
    "__OWNER_APPROVED_DATABASE_URL_SECRET__": "nebula-demo-database-url",
    "__OWNER_APPROVED_JWT_SECRET__": "nebula-demo-jwt-secret",
    "__OWNER_APPROVED_RPC_SECRET__": "nebula-demo-rpc",
    "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET__": "nebula-demo-r2-access-key",
    "__OWNER_APPROVED_R2_SECRET_KEY_SECRET__": "nebula-demo-r2-secret-key",
}


class RenderError(ValueError):
    """Raised when owner configuration is incomplete or unsafe."""


def read_value(config_dir: Path, name: str) -> str:
    path = config_dir / name
    if not path.is_file():
        raise RenderError(f"missing owner configuration: {name}")
    if path.stat().st_mode & 0o077:
        raise RenderError(f"owner configuration is not mode 0600: {name}")
    value = path.read_text(encoding="utf-8")
    if not value or "\n" in value or "\r" in value or "__" in value:
        raise RenderError(f"invalid or placeholder owner configuration: {name}")
    return value


def render(template: Path, replacements: dict[str, str], output: Path) -> None:
    text = template.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    unresolved = sorted(set(PLACEHOLDER.findall(text)))
    if unresolved:
        raise RenderError("unresolved placeholders: " + ", ".join(unresolved))
    json.loads(text)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
    os.chmod(output, 0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="render the Cloud Run service")
    parser.add_argument("--rewrite-output", type=Path, help="render the Vercel rewrite")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.output) == bool(args.rewrite_output):
        raise SystemExit("choose exactly one of --output or --rewrite-output")
    try:
        if args.output:
            replacements = {
                placeholder: read_value(args.config_dir, name)
                for placeholder, name in SERVICE_VALUES.items()
            }
            replacements.update(FIXED_VALUES)
            render(SERVICE_TEMPLATE, replacements, args.output)
        else:
            origin = read_value(args.config_dir, "CLOUD_RUN_ORIGIN")
            render(
                REWRITE_TEMPLATE,
                {"__OWNER_APPROVED_CLOUD_RUN_HTTPS_ORIGIN__": origin.rstrip("/")},
                args.rewrite_output,
            )
    except (OSError, RenderError, json.JSONDecodeError) as exc:
        raise SystemExit(f"configuration render refused: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
