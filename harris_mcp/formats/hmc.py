"""HMC adapter — Harris Matrix Composer native format.

HMC files are produced by the proprietary Harris Matrix Composer application.
The format is not openly specified. GraphML payloads (what HMC 2.x
writes) are read by `hmc_units`; anything else goes through a best-effort XML
sniffer that extracts contexts and `above` edges from the structures we have
observed in the wild; it is intentionally conservative and will raise a clear
`NotImplementedError` rather than silently mis-parse an unknown variant.

For lossless workflows, export your HMC project to CSV or XLSX from inside
Harris Matrix Composer and load that file instead — or round-trip through
HMDP using `save_matrix(..., fmt="hmdp")`.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Context, Matrix, Relation
from ..registry import new_id
from . import hmc_units


def _best_effort_xml(text: str, p: Path) -> Matrix:
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise NotImplementedError(
            f"{p} does not look like XML-based HMC; export to CSV/XLSX from "
            "Harris Matrix Composer and load that instead."
        ) from exc

    if hmc_units.is_graphml(root):
        return hmc_units.from_graphml(root, p)

    m = Matrix(id=new_id(hint=p.stem), name=p.stem, path=str(p))

    # Heuristic: nodes named 'unit'/'context'/'su' carry an 'id' attribute.
    found_any = False
    for tag in ("unit", "context", "su", "Unit", "Context", "SU"):
        for node in root.iter(tag):
            ctx_id = node.attrib.get("id") or node.attrib.get("name") or node.findtext("id")
            if not ctx_id:
                continue
            found_any = True
            attrs = dict(node.attrib)
            m.add_context(
                Context(
                    id=str(ctx_id),
                    type=attrs.pop("type", None),
                    phase=attrs.pop("phase", None),
                    period=attrs.pop("period", None),
                    description=node.findtext("description"),
                    attrs={k: v for k, v in attrs.items() if k not in {"id", "name"}},
                )
            )

    for tag in ("edge", "relation", "above", "Edge", "Relation"):
        for node in root.iter(tag):
            a = node.attrib.get("a") or node.attrib.get("from") or node.attrib.get("above")
            b = node.attrib.get("b") or node.attrib.get("to") or node.attrib.get("below")
            if not (a and b):
                continue
            found_any = True
            kind = node.attrib.get("kind") or ("above" if tag.lower() == "above" else "above")
            m.add_relation(Relation(a=str(a), b=str(b), kind=kind))

    if not found_any:
        raise NotImplementedError(
            f"Could not extract Harris matrix data from {p}. The HMC binary/"
            "XML variant is not yet supported; export to CSV/XLSX/HMDP from "
            "Harris Matrix Composer and load that instead."
        )

    m.rebuild_indexes()
    return m


def load(path: str | Path) -> Matrix:
    p = Path(path)
    raw = p.read_bytes()
    # XML-based HMC: try decoding as text and sniffing
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise NotImplementedError(
                f"{p} is binary HMC; not yet supported. Export to CSV/XLSX "
                "from Harris Matrix Composer."
            ) from exc
    return _best_effort_xml(text, p)


def dump(matrix: Matrix, path: str | Path) -> None:
    raise NotImplementedError(
        "Writing HMC files is not supported (closed format). "
        "Save to HMDP/CSV/XLSX and import into Harris Matrix Composer."
    )
