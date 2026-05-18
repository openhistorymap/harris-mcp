"""Format adapters.

Each adapter exposes `load(path) -> Matrix` and `dump(matrix, path) -> None`.
HMDP is the canonical pivot; everything else is best-effort.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Matrix
from . import csv as csv_fmt
from . import hmc as hmc_fmt
from . import hmcx as hmcx_fmt
from . import hmdp as hmdp_fmt
from . import xlsx as xlsx_fmt

_LOADERS = {
    "hmdp": hmdp_fmt.load,
    "json": hmdp_fmt.load,
    "csv": csv_fmt.load,
    "xlsx": xlsx_fmt.load,
    "hmc": hmc_fmt.load,
    "hmcx": hmcx_fmt.load,
}

_DUMPERS = {
    "hmdp": hmdp_fmt.dump,
    "json": hmdp_fmt.dump,
    "csv": csv_fmt.dump,
    "xlsx": xlsx_fmt.dump,
    "hmc": hmc_fmt.dump,
    "hmcx": hmcx_fmt.dump,
}

SUPPORTED = sorted(set(_LOADERS) | set(_DUMPERS))


def detect(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower().lstrip(".")
    if suffix == "json":
        # Could be HMDP or arbitrary JSON; HMDP is the loader we have.
        return "hmdp"
    if suffix in _LOADERS:
        return suffix
    # Directory containing contexts.csv + relations.csv is treated as csv.
    if p.is_dir() and (p / "contexts.csv").exists():
        return "csv"
    raise ValueError(f"Unrecognised format for path: {path!r}")


def load(path: str | Path, fmt: str = "auto") -> Matrix:
    if fmt == "auto":
        fmt = detect(path)
    if fmt not in _LOADERS:
        raise ValueError(f"No loader for format {fmt!r}")
    return _LOADERS[fmt](path)


def dump(matrix: Matrix, path: str | Path, fmt: str = "auto") -> None:
    if fmt == "auto":
        fmt = detect(path)
    if fmt not in _DUMPERS:
        raise ValueError(f"No dumper for format {fmt!r}")
    _DUMPERS[fmt](matrix, path)
