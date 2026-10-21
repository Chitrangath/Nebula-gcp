#!/usr/bin/env python3
"""Validate the local GCP demo service and same-origin rewrite contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PLACEHOLDER_PATTERN = re.compile(r"__[A-Z0-9_]+__")
IMAGE_DIGEST_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._/-]*@[sS][hH][aA]256:[0-9a-f]{64}$"
)
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
R2_ACCOUNT_PATTERN = re.compile(r"^[0-9a-f]{32}$")
BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class ValidationError(ValueError):
    """Raised when a GCP demo configuration violates its public contract."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: not valid JSON-compatible YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidationError(f"{path}: document root must be an object")
    return document


def placeholders(value: object) -> set[str]:
    return set(PLACEHOLDER_PATTERN.findall(json.dumps(value, sort_keys=True)))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_service(service: dict[str, Any], *, template_mode: bool) -> None:
    require(
        service.get("apiVersion") == "serving.knative.dev/v1",
        "unsupported Cloud Run service apiVersion",
    )
    require(service.get("kind") == "Service", "Cloud Run document must be a Service")
    metadata = service.get("metadata", {})
    spec = service.get("spec", {})
    revision = spec.get("template", {})
    annotations = revision.get("metadata", {}).get("annotations", {})
    revision_spec = revision.get("spec", {})
    containers = revision_spec.get("containers", [])

    require(
        metadata.get("annotations", {}).get("run.googleapis.com/ingress") == "all",
        "public Vercel upstream requires Cloud Run ingress=all",
    )
    require(
        annotations.get("autoscaling.knative.dev/minScale") == "0",
        "minimum instances must equal zero",
    )
    require(
        annotations.get("autoscaling.knative.dev/maxScale") == "2",
        "maximum instances must equal two",
    )
    require(
        annotations.get("run.googleapis.com/cpu-throttling") == "true",
        "request-based CPU throttling must be enabled",
    )
    require(
        len(containers) == 1 and containers[0].get("name") == "api",
        "profile must contain exactly one API container",
    )

    container = containers[0]
    environment = {item.get("name"): item for item in container.get("env", [])}
    runner_settings = {
        name
        for name in environment
        if isinstance(name, str) and "RUNNER" in name and name != "RUNNERS_ENABLED"
    }
    require(
        not runner_settings,
        "runner configuration is forbidden in the GCP demo profile",
    )
    require(
        environment.get("RUNNERS_ENABLED", {}).get("value") == "false",
        "RUNNERS_ENABLED must remain false",
    )
    command_text = " ".join(
        [*container.get("command", []), *container.get("args", [])]
    ).lower()
    require(
        "runner" not in command_text,
        "runner commands are forbidden in the GCP demo profile",
    )
    require(
        "${PORT:?Cloud Run PORT is required}" in " ".join(container.get("args", [])),
        "API command must consume Cloud Run PORT",
    )
    require(
        container.get("startupProbe", {}).get("httpGet", {}).get("path") == "/ready",
        "startup probe must use /ready",
    )
    require(
        container.get("resources", {}).get("limits") == {"cpu": "1", "memory": "512Mi"},
        "resource limits must remain 1 CPU and 512Mi",
    )
    for name in (
        "DATABASE_URL",
        "JWT_SECRET",
        "ARBITRUM_SEPOLIA_RPC",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ):
        require(
            "valueFrom" in environment.get(name, {}),
            f"{name} must be a secret reference",
        )
        require(
            "value" not in environment.get(name, {}),
            f"{name} must not contain a literal value",
        )

    secret_refs = {
        name: environment[name]["valueFrom"]["secretKeyRef"]
        for name in (
            "DATABASE_URL",
            "JWT_SECRET",
            "ARBITRUM_SEPOLIA_RPC",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        )
    }
    require(
        environment.get("STORAGE_ADAPTER", {}).get("value") == "s3",
        "STORAGE_ADAPTER must equal s3 for the deployed demo profile",
    )
    require(
        "LOCAL_STORAGE_PATH" not in environment,
        "deployed demo profile must not configure FileStorage",
    )

    image = container.get("image", "")
    service_account = revision_spec.get("serviceAccountName", "")
    frontend_url = environment.get("FRONTEND_URL", {}).get("value", "")
    if template_mode:
        require(
            image == "__OWNER_APPROVED_IMAGE_DIGEST__",
            "image template placeholder changed",
        )
        require(
            service_account == "__OWNER_APPROVED_RUNTIME_SERVICE_ACCOUNT__",
            "runtime identity placeholder changed",
        )
        require(
            frontend_url == "__REAL_VERCEL_HTTPS_ORIGIN_REQUIRED__",
            "frontend origin placeholder changed",
        )
        expected_secret_refs = {
            "DATABASE_URL": {
                "name": "__OWNER_APPROVED_DATABASE_URL_SECRET__",
                "key": "__OWNER_APPROVED_DATABASE_URL_SECRET_VERSION__",
            },
            "JWT_SECRET": {
                "name": "__OWNER_APPROVED_JWT_SECRET__",
                "key": "__OWNER_APPROVED_JWT_SECRET_VERSION__",
            },
            "ARBITRUM_SEPOLIA_RPC": {
                "name": "__OWNER_APPROVED_RPC_SECRET__",
                "key": "__OWNER_APPROVED_RPC_SECRET_VERSION__",
            },
            "R2_ACCESS_KEY_ID": {
                "name": "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET__",
                "key": "__OWNER_APPROVED_R2_ACCESS_KEY_SECRET_VERSION__",
            },
            "R2_SECRET_ACCESS_KEY": {
                "name": "__OWNER_APPROVED_R2_SECRET_KEY_SECRET__",
                "key": "__OWNER_APPROVED_R2_SECRET_KEY_SECRET_VERSION__",
            },
        }
        require(
            secret_refs == expected_secret_refs, "runtime secret placeholders changed"
        )
        expected_values = {
            "NEBULA_PAYMENT_CONTRACT": "__OWNER_APPROVED_CONTRACT_ADDRESS__",
            "CONTRACT_DEPLOYMENT_BLOCK": "__OWNER_APPROVED_CONTRACT_DEPLOYMENT_BLOCK__",
            "CONTRACT_OWNER_ADDRESS": "__OWNER_APPROVED_CONTRACT_OWNER_ADDRESS__",
            "CONTRACT_VERIFIER_ADDRESS": "__OWNER_APPROVED_CONTRACT_VERIFIER_ADDRESS__",
            "R2_ACCOUNT_ID": "__OWNER_APPROVED_R2_ACCOUNT_ID__",
            "R2_BUCKET_NAME": "__OWNER_APPROVED_R2_BUCKET_NAME__",
            "OBJECT_STORAGE_PREFIX": "__OWNER_APPROVED_STORAGE_PREFIX__",
        }
        for name, expected in expected_values.items():
            require(
                environment.get(name, {}).get("value") == expected,
                f"{name} placeholder changed",
            )
    else:
        require(
            IMAGE_DIGEST_PATTERN.fullmatch(image) is not None,
            "image must be pinned by sha256 digest",
        )
        require(
            "@" in service_account
            and service_account.endswith(".iam.gserviceaccount.com"),
            "runtime service account must be owner-approved",
        )
        validate_https_origin(frontend_url, "FRONTEND_URL")
        for label, secret_ref in secret_refs.items():
            require(
                bool(secret_ref.get("name")), f"{label} secret name must be non-empty"
            )
            require(
                str(secret_ref.get("key", "")).isdigit(),
                f"{label} secret version must be numeric and pinned",
            )
        require(
            environment.get("CHAIN_ID", {}).get("value") == "421614",
            "CHAIN_ID must equal 421614",
        )
        require(
            environment.get("USDC_SEPOLIA_ADDRESS", {}).get("value")
            == "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
            "USDC_SEPOLIA_ADDRESS does not match the preserved deployment fact",
        )
        for name in (
            "NEBULA_PAYMENT_CONTRACT",
            "CONTRACT_OWNER_ADDRESS",
            "CONTRACT_VERIFIER_ADDRESS",
        ):
            require(
                ADDRESS_PATTERN.fullmatch(environment.get(name, {}).get("value", ""))
                is not None,
                f"{name} must be a deployed address",
            )
        require(
            str(
                environment.get("CONTRACT_DEPLOYMENT_BLOCK", {}).get("value", "")
            ).isdigit()
            and int(environment["CONTRACT_DEPLOYMENT_BLOCK"]["value"]) > 0,
            "CONTRACT_DEPLOYMENT_BLOCK must be a positive integer",
        )
        require(
            R2_ACCOUNT_PATTERN.fullmatch(
                environment.get("R2_ACCOUNT_ID", {}).get("value", "")
            )
            is not None,
            "R2_ACCOUNT_ID must be an owner-approved account identifier",
        )
        require(
            BUCKET_PATTERN.fullmatch(
                environment.get("R2_BUCKET_NAME", {}).get("value", "")
            )
            is not None,
            "R2_BUCKET_NAME must be an owner-approved private bucket name",
        )
        require(
            environment.get("OBJECT_STORAGE_REGION", {}).get("value") == "auto",
            "R2 region must equal auto",
        )
        prefix = environment.get("OBJECT_STORAGE_PREFIX", {}).get("value", "")
        require(
            bool(prefix) and "/" not in prefix and ".." not in prefix,
            "storage prefix must be one safe segment",
        )
        require(
            environment.get("OBJECT_STORAGE_CAPABILITY_TTL_SECONDS", {}).get("value")
            == "300",
            "storage capability TTL must equal 300 seconds",
        )
        require(
            environment.get("JWT_EXPIRY_HOURS", {}).get("value") == "24",
            "JWT expiry must equal 24 hours",
        )
        require(
            environment.get("JWT_REFRESH_EXPIRY_HOURS", {}).get("value") == "168",
            "JWT refresh expiry must equal 168 hours",
        )


def validate_https_origin(value: str, label: str) -> None:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValidationError(f"{label} is not a valid URL: {exc}") from exc
    require(parsed.scheme == "https", f"{label} must use https")
    require(bool(parsed.hostname), f"{label} must include a hostname")
    require(
        parsed.username is None and parsed.password is None,
        f"{label} must not contain credentials",
    )
    require(
        not parsed.query and not parsed.fragment,
        f"{label} must not contain a query or fragment",
    )
    require(parsed.path in ("", "/"), f"{label} must be an origin without a path")


def validate_rewrite(rewrite: dict[str, Any], *, template_mode: bool) -> None:
    rewrites = rewrite.get("rewrites", [])
    require(len(rewrites) >= 2, "rewrite contract must include API and SPA rules")
    require(rewrites[0].get("source") == "/api/v1/:path*", "API rewrite must be first")
    require(
        rewrites[1].get("source") == "/:path*"
        and rewrites[1].get("destination") == "/index.html",
        "SPA fallback must follow the API rewrite",
    )
    destination = rewrites[0].get("destination", "")
    if template_mode:
        require(
            destination == "__OWNER_APPROVED_CLOUD_RUN_HTTPS_ORIGIN__/v1/:path*",
            "Cloud Run origin placeholder changed",
        )
    else:
        suffix = "/v1/:path*"
        require(
            destination.endswith(suffix), "API rewrite must map to backend /v1/:path*"
        )
        validate_https_origin(destination[: -len(suffix)], "Cloud Run origin")

    header_sets = rewrite.get("headers", [])
    require(
        header_sets and header_sets[0].get("source") == "/api/v1/:path*",
        "API cache policy is missing",
    )
    headers = {
        item.get("key", "").lower(): item.get("value")
        for item in header_sets[0].get("headers", [])
    }
    require(
        headers.get("x-vercel-enable-rewrite-caching") == "0",
        "API rewrite caching must be disabled",
    )
    require(
        headers.get("cache-control") == "no-store",
        "API responses must retain no-store policy",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--rewrite", type=Path)
    parser.add_argument(
        "--service-only",
        action="store_true",
        help="validate only a materialized Cloud Run service before any Vercel cutover",
    )
    parser.add_argument(
        "--template", action="store_true", help="validate inert tracked templates"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        service = load_object(args.service)
        require(
            args.service_only or args.rewrite is not None,
            "--rewrite is required unless --service-only is selected",
        )
        require(
            not (args.service_only and args.rewrite),
            "--service-only cannot be combined with --rewrite",
        )
        rewrite = None if args.service_only else load_object(args.rewrite)
        unresolved = placeholders({"service": service, "rewrite": rewrite})
        if unresolved and not args.template:
            raise ValidationError(
                "owner-approved values are still placeholders: "
                + ", ".join(sorted(unresolved))
            )
        validate_service(service, template_mode=args.template)
        if rewrite is not None:
            validate_rewrite(rewrite, template_mode=args.template)
    except (AttributeError, KeyError, TypeError) as exc:
        print(
            f"GCP demo configuration rejected: configuration shape is invalid: {exc}",
            file=sys.stderr,
        )
        return 1
    except ValidationError as exc:
        print(f"GCP demo configuration rejected: {exc}", file=sys.stderr)
        return 1
    print("GCP demo configuration contract is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
