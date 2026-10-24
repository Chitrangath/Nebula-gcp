"""Validation and canonicalization for exact job input bytes."""

import re
import struct
from dataclasses import dataclass
from pathlib import PurePath
from typing import Final

from fastapi import UploadFile

READ_CHUNK_BYTES: Final = 64 * 1024
MAX_IMAGE_DIMENSION: Final = 16_384
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_FORMATS = {
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    "jpg": ("image/jpeg", b"\xff\xd8"),
    "jpeg": ("image/jpeg", b"\xff\xd8"),
}


class InputUploadError(ValueError):
    """The submitted bytes do not satisfy approved model input constraints."""


class InputTooLargeError(InputUploadError):
    """The submitted bytes exceed the approved model input limit."""


@dataclass(frozen=True)
class AcceptedInput:
    """Canonical accepted input returned by the upload interface."""

    data: bytes
    extension: str
    content_type: str
    width: int
    height: int


async def accept_text_upload(
    upload: UploadFile, *, supported_formats: list[str], max_size_bytes: int,
) -> AcceptedInput:
    """Accept exact bounded UTF-8 text for BERT, rejecting binary/empty uploads."""
    filename = upload.filename or ""
    if not _SAFE_FILENAME.fullmatch(filename) or not filename.lower().endswith(".txt"):
        raise InputUploadError("use a safe .txt filename")
    if "txt" not in supported_formats or upload.content_type != "text/plain":
        raise InputUploadError("BERT requires a text/plain .txt upload")
    data = await upload.read(min(max_size_bytes, 65536) + 1)
    if len(data) > min(max_size_bytes, 65536):
        raise InputTooLargeError("text input exceeds the 64 KiB limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InputUploadError("text must be valid UTF-8") from exc
    if not text.strip() or "\0" in text:
        raise InputUploadError("text must be nonempty and contain no NUL bytes")
    return AcceptedInput(data, "txt", "text/plain", 0, 0)


async def accept_image_upload(
    upload: UploadFile,
    *,
    supported_formats: list[str],
    max_size_bytes: int,
) -> AcceptedInput:
    """Read a bounded image upload and validate name, type, magic, and dimensions."""
    filename = upload.filename or ""
    if not _SAFE_FILENAME.fullmatch(filename) or PurePath(filename).name != filename:
        raise InputUploadError("invalid input filename")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    approved = {value.lower().lstrip(".") for value in supported_formats}
    if extension not in approved or extension not in _FORMATS:
        raise InputUploadError("input extension is not approved for this model")
    expected_mime, magic = _FORMATS[extension]
    if upload.content_type != expected_mime:
        raise InputUploadError("input MIME type does not match its extension")

    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > max_size_bytes:
            raise InputTooLargeError("input exceeds the model size limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(magic):
        raise InputUploadError("input magic bytes do not match its declared format")
    width, height = _image_dimensions(data, extension)
    if not (0 < width <= MAX_IMAGE_DIMENSION and 0 < height <= MAX_IMAGE_DIMENSION):
        raise InputUploadError("input image dimensions are outside the safe range")
    return AcceptedInput(data, extension, expected_mime, width, height)


def _image_dimensions(data: bytes, extension: str) -> tuple[int, int]:
    if extension == "png":
        if len(data) < 33 or data[12:16] != b"IHDR" or not data.endswith(b"IEND\xaeB`\x82"):
            raise InputUploadError("truncated or malformed PNG input")
        return struct.unpack(">II", data[16:24])

    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            raise InputUploadError("truncated or malformed JPEG input")
        marker = data[offset + 1]
        offset += 2
        if marker in (0xD8, 0xD9):
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in range(0xC0, 0xC4):
            if length < 7:
                break
            return int.from_bytes(data[offset + 3 : offset + 5], "big"), int.from_bytes(
                data[offset + 5 : offset + 7], "big"
            )
        offset += length
    raise InputUploadError("truncated or malformed JPEG input")
