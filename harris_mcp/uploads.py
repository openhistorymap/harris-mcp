"""Matrices sent by a client as file contents rather than server paths.

Each upload lands in its own folder under the upload root and is loaded
with the ordinary format detection: one file is loaded as that file, several
as a folder (paired CSV tables, an hm project, a Frictionless package).

The server may be public and unauthenticated, so uploads are bounded: plain
file names only, a byte and a file-count cap, and only the most recent
uploads are kept on disk.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from . import formats, registry
from .model import Matrix

ROOT = Path(os.environ.get("HARRIS_UPLOAD_DIR") or Path(tempfile.gettempdir()) / "harris-uploads")
MAX_BYTES = int(os.environ.get("HARRIS_UPLOAD_MAX_BYTES", 10 * 1024 * 1024))
MAX_FILES = int(os.environ.get("HARRIS_UPLOAD_MAX_FILES", 20))
KEEP = max(1, int(os.environ.get("HARRIS_UPLOAD_KEEP", 100)))

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,127}$")
BINARY = {".xlsx", ".hmcx", ".zip"}


class UploadError(ValueError):
    pass


def _decode(name: str, content: str, encoding: Literal["text", "base64"]) -> bytes:
    if encoding == "base64":
        try:
            return base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UploadError(f"{name}: not valid base64") from exc
    if Path(name).suffix.lower() in BINARY:
        raise UploadError(f"{name}: binary format, send it with encoding='base64'")
    return content.encode("utf-8")


def _prune() -> None:
    folders = sorted((p for p in ROOT.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    for old in folders[:-KEEP]:
        shutil.rmtree(old, ignore_errors=True)


def load(files: dict[str, str], encoding: Literal["text", "base64"] = "text",
         fmt: str = "auto", name: str | None = None) -> Matrix:
    """Write `files` (file name -> content) to a fresh upload folder and load it."""
    if not files:
        raise UploadError("no files given")
    if len(files) > MAX_FILES:
        raise UploadError(f"too many files ({len(files)}; at most {MAX_FILES})")
    for fname in files:
        if not _NAME.match(fname) or ".." in fname:
            raise UploadError(f"{fname!r}: use a plain file name (letters, digits, . _ - + ( ) and spaces)")
    data = {fname: _decode(fname, content, encoding) for fname, content in files.items()}
    size = sum(len(b) for b in data.values())
    if size > MAX_BYTES:
        raise UploadError(f"upload too large ({size:,} bytes; at most {MAX_BYTES:,})")

    ROOT.mkdir(parents=True, exist_ok=True)
    folder = ROOT / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    try:
        for fname, blob in data.items():
            (folder / fname).write_bytes(blob)
        target = folder / next(iter(data)) if len(data) == 1 else folder
        matrix = formats.load(target, fmt=fmt)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    # Name the handle after the upload, not the timestamped folder.
    hint = re.sub(r"[^A-Za-z0-9_-]+", "-", name or Path(next(iter(data))).stem).strip("-")[:40]
    matrix.id = registry.new_id(hint=hint or "upload")
    if name:
        matrix.name = name
    _prune()
    return matrix
