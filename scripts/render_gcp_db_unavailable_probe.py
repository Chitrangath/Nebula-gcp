#!/usr/bin/env python3
"""Render an isolated Cloud Run service that proves database-unavailable readiness."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

SERVICE_NAME = re.compile(r"^[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DUMMY_DATABASE_URL = "postgresql+asyncpg://probe:probe@127.0.0.1:1/unavailable"


class ProbeRenderError(ValueError):
    """Raised when an isolated readiness probe cannot be rendered safely."""


def load_service(path: Path) -> dict[str, Any]:
    try:
        service = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeRenderError("source service is not valid JSON") from exc
    if not isinstance(service, dict) or service.get("kind") != "Service":
        raise ProbeRenderError("source must be a Cloud Run Service")
    return service


def render_probe(service: dict[str, Any], probe_name: str) -> dict[str, Any]:
    if SERVICE_NAME.fullmatch(probe_name) is None:
        raise ProbeRenderError("probe service name is invalid")

    # A JSON round trip gives the probe an independent tree and rejects values
    # that cannot be represented in the deployment document.
    probe = json.loads(json.dumps(service))
    try:
        source_name = probe["metadata"]["name"]
        revision = probe["spec"]["template"]
        container = revision["spec"]["containers"][0]
        environment = container["env"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProbeRenderError("source service structure is incomplete") from exc
    if probe_name == source_name:
        raise ProbeRenderError("probe must not replace the production service")
    if len(probe["spec"]["template"]["spec"].get("containers", [])) != 1:
        raise ProbeRenderError("probe requires exactly one API container")

    database_entries = [item for item in environment if item.get("name") == "DATABASE_URL"]
    if len(database_entries) != 1:
        raise ProbeRenderError("source must contain exactly one DATABASE_URL")

    probe["metadata"]["name"] = probe_name
    revision.setdefault("metadata", {}).setdefault("annotations", {})[
        "autoscaling.knative.dev/maxScale"
    ] = "1"
    database_entries[0].clear()
    database_entries[0].update({"name": "DATABASE_URL", "value": DUMMY_DATABASE_URL})
    container["startupProbe"] = {
        "httpGet": {"path": "/live", "port": 8080},
        "initialDelaySeconds": 0,
        "timeoutSeconds": 2,
        "periodSeconds": 5,
        "failureThreshold": 6,
    }
    probe["spec"]["traffic"] = [{"latestRevision": True, "percent": 100}]
    return probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--probe-service", required=True)
    args = parser.parse_args()
    try:
        probe = render_probe(load_service(args.service), args.probe_service)
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.output.write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
        os.chmod(args.output, 0o600)
    except (OSError, ProbeRenderError) as exc:
        raise SystemExit(f"database failure probe render refused: {exc}") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
