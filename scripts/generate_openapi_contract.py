#!/usr/bin/env python3
"""Generate or verify the checked FastAPI OpenAPI document and browser types."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OPENAPI_PATH = BACKEND / "openapi.json"
MANIFEST_PATH = BACKEND / "openapi.manifest.json"
TYPES_PATH = ROOT / "frontend" / "src" / "api" / "schema.d.ts"
GENERATOR = ROOT / "frontend" / "node_modules" / ".bin" / "openapi-typescript"


def render_openapi() -> str:
    previous_cwd = Path.cwd()
    backend_path = str(BACKEND)
    added_backend_path = backend_path not in sys.path
    if added_backend_path:
        sys.path.insert(0, backend_path)
    try:
        os.chdir(BACKEND)
        from app.main import app
    finally:
        os.chdir(previous_cwd)
        if added_backend_path:
            sys.path.remove(backend_path)

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def source_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted((BACKEND / "app").rglob("*.py")):
        digest.update(path.relative_to(BACKEND).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def render_manifest(rendered_openapi: str) -> str:
    return json.dumps(
        {
            "openapi_sha256": hashlib.sha256(rendered_openapi.encode()).hexdigest(),
            "source_sha256": source_sha256(),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def generate_types(openapi_path: Path, output_path: Path) -> None:
    if not GENERATOR.is_file():
        raise SystemExit("Missing frontend OpenAPI generator; run npm install in frontend/")
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    subprocess.run(
        [str(GENERATOR), str(openapi_path), "--output", str(output_path)],
        cwd=ROOT / "frontend",
        env=env,
        check=True,
    )


def check_equal(actual: str, expected_path: Path) -> None:
    if not expected_path.is_file() or expected_path.read_text() != actual:
        raise SystemExit(f"Generated contract is stale: {expected_path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail instead of updating stale artifacts")
    args = parser.parse_args()
    rendered = render_openapi()
    manifest = render_manifest(rendered)

    if args.check:
        check_equal(rendered, OPENAPI_PATH)
        check_equal(manifest, MANIFEST_PATH)
        with tempfile.TemporaryDirectory() as tmp:
            temporary_openapi = Path(tmp) / "openapi.json"
            temporary_types = Path(tmp) / "schema.d.ts"
            temporary_openapi.write_text(rendered)
            generate_types(temporary_openapi, temporary_types)
            check_equal(temporary_types.read_text(), TYPES_PATH)
        print("OpenAPI document and browser types are current")
        return 0

    OPENAPI_PATH.write_text(rendered)
    MANIFEST_PATH.write_text(manifest)
    generate_types(OPENAPI_PATH, TYPES_PATH)
    print(f"Wrote {OPENAPI_PATH.relative_to(ROOT)} and {TYPES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
