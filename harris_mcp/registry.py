"""Process-local registry of open matrices and cross-document correspondences."""

from __future__ import annotations

import uuid
from typing import Iterable

from .model import Correspondence, Matrix

_matrices: dict[str, Matrix] = {}
_correspondences: list[Correspondence] = []


def register(matrix: Matrix) -> str:
    if matrix.id in _matrices:
        return matrix.id
    _matrices[matrix.id] = matrix
    return matrix.id


def new_id(hint: str | None = None) -> str:
    base = uuid.uuid4().hex[:8]
    return f"{hint}-{base}" if hint else base


def get(matrix_id: str) -> Matrix:
    if matrix_id not in _matrices:
        raise KeyError(f"No open matrix with id {matrix_id!r}")
    return _matrices[matrix_id]


def close(matrix_id: str) -> None:
    _matrices.pop(matrix_id, None)


def list_ids() -> list[str]:
    return list(_matrices.keys())


def all_matrices() -> Iterable[Matrix]:
    return _matrices.values()


def add_correspondence(c: Correspondence) -> Correspondence:
    _correspondences.append(c)
    return c


def correspondences(matrix_id: str | None = None, ctx: str | None = None) -> list[Correspondence]:
    out = _correspondences
    if matrix_id is not None:
        out = [c for c in out if c.matrix_a == matrix_id or c.matrix_b == matrix_id]
    if ctx is not None:
        out = [c for c in out if c.ctx_a == ctx or c.ctx_b == ctx]
    return list(out)


def reset() -> None:
    """Test hook."""
    _matrices.clear()
    _correspondences.clear()
