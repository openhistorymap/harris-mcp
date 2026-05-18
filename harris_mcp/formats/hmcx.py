"""HMCX adapter — newer Harris Matrix Composer container format.

HMCX is typically a zipped bundle of XML resources. This adapter unpacks
the archive in memory, looks for an XML payload (commonly ``matrix.xml`` or
``project.xml``), and hands it to the HMC adapter's best-effort XML reader.

As with HMC, the format is proprietary and undocumented; we raise a clear
``NotImplementedError`` on unknown layouts rather than silently mis-parse.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from ..model import Matrix
from . import hmc as hmc_fmt


_CANDIDATE_PAYLOADS = ("matrix.xml", "project.xml", "data.xml", "content.xml")


def load(path: str | Path) -> Matrix:
    p = Path(path)
    raw = p.read_bytes()
    if not zipfile.is_zipfile(BytesIO(raw)):
        # Some HMCX files are just XML with a different extension.
        return hmc_fmt._best_effort_xml(raw.decode("utf-8", errors="replace"), p)

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        names = {n.lower(): n for n in zf.namelist()}
        chosen: str | None = None
        for candidate in _CANDIDATE_PAYLOADS:
            if candidate in names:
                chosen = names[candidate]
                break
        if chosen is None:
            xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xmls:
                raise NotImplementedError(
                    f"{p} is a HMCX archive but contains no XML payload we recognise."
                )
            chosen = xmls[0]
        text = zf.read(chosen).decode("utf-8", errors="replace")
    return hmc_fmt._best_effort_xml(text, p)


def dump(matrix: Matrix, path: str | Path) -> None:
    raise NotImplementedError(
        "Writing HMCX files is not supported (closed format). "
        "Save to HMDP/CSV/XLSX and import into Harris Matrix Composer."
    )
