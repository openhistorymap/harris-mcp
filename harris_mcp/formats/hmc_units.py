"""Harris Matrix Composer unit model, shared by its two open-ish encodings.

HMC 2.x stores a matrix as GraphML (``matrix.xml`` inside an ``.hmcx``
zip) and exports it as a semicolon-separated "CSV". Both describe the same
things, verified against the Ulm-Eggingen files (Rosenstock 2022,
doi:10.5281/zenodo.4744471):

* units typed ``DEPOSIT``, ``INTERFACE``, ... plus the three pseudo-units
  ``TOP_SURFACE``, ``UNEXCAVATED`` and ``GEOLOGY``, kept as contexts;
* ``PHASE_GROUP`` / ``PERIOD_GROUP`` containers, which are not contexts but
  become the ``phase`` / ``period`` of the units nested in them;
* ``ABOVE`` relations (GraphML source above target) and ``CONTEMPORARY``
  ones.
"""

from __future__ import annotations

import csv as _csv
from pathlib import Path
from xml.etree import ElementTree as ET

from ..model import Context, Matrix, Relation
from ..registry import new_id

_GRAPHML = "{http://graphml.graphdrawing.org/xmlns/graphml}"
_GROUPS = {"PHASE_GROUP": "phase", "PERIOD_GROUP": "period"}


def is_graphml(root: ET.Element) -> bool:
    return root.tag == f"{_GRAPHML}graphml"


def _build(
    p: Path,
    units: dict[str, dict],
    parent: dict[str, str],
    above: list[tuple[str, str]],
    contemporary: list[tuple[str, str]],
) -> Matrix:
    m = Matrix(id=new_id(hint=p.stem), name=p.stem, path=str(p))
    for uid, u in units.items():
        if u["type"] in _GROUPS:
            continue
        kwargs: dict[str, str] = {}
        node = parent.get(uid)
        while node is not None:
            key = _GROUPS.get(units.get(node, {}).get("type", ""))
            if key:
                kwargs.setdefault(key, node)
            node = parent.get(node)
        attrs = {k: v for k, v in u.items() if k not in ("type", "description") and v not in ("", None)}
        m.add_context(Context(
            id=uid,
            type=u["type"].lower(),
            description=u.get("description") or None,
            attrs=attrs,
            **kwargs,
        ))
    for a, b in dict.fromkeys(above):
        m.add_relation(Relation(a=a, b=b, kind="above"))
    seen: set[frozenset] = set()
    for a, b in contemporary:
        if a != b and frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            m.add_relation(Relation(a=a, b=b, kind="contemporary"))
    if not m.contexts:
        raise ValueError(f"{p} contains no Harris Matrix Composer units")
    m.rebuild_indexes()
    return m


def from_graphml(root: ET.Element, p: Path) -> Matrix:
    units: dict[str, dict] = {}
    parent: dict[str, str] = {}

    def walk(graph: ET.Element, owner: str | None) -> None:
        for node in graph.findall(f"{_GRAPHML}node"):
            info = node.find(f"{_GRAPHML}data/hmcnode")
            uid = (node.get("id") or "").strip()  # HMC keeps stray spaces in ids
            if info is None or not uid:
                continue
            units[uid] = {
                "type": info.get("type", "DEPOSIT"),
                "name": info.get("name", ""),
                "description": info.get("description", ""),
                "layer": info.get("layer", ""),
            }
            if owner is not None:
                parent[uid] = owner
            for sub in node.findall(f"{_GRAPHML}graph"):
                walk(sub, uid)

    for graph in root.findall(f"{_GRAPHML}graph"):
        walk(graph, None)

    above, contemporary = [], []
    for edge in root.iter(f"{_GRAPHML}edge"):
        info = edge.find(f"{_GRAPHML}data/hmcedge")
        kind = info.get("type") if info is not None else "ABOVE"
        pair = (edge.get("source", "").strip(), edge.get("target", "").strip())
        if kind == "ABOVE":
            above.append(pair)
        elif kind == "CONTEMPORARY":
            contemporary.append(pair)
        else:
            raise NotImplementedError(f"{p}: unknown HMC edge type {kind!r}")
    return _build(p, units, parent, above, contemporary)


def _split(cell: str) -> list[str]:
    return [x.strip() for x in cell.split(",") if x.strip()]


def from_csv_export(text: str, p: Path) -> Matrix:
    units: dict[str, dict] = {}
    parent: dict[str, str] = {}
    above, contemporary = [], []
    header: list[str] = []
    for row in _csv.reader(text.splitlines(), delimiter=";"):
        if not row:
            continue
        if row[0] == "HEADER":
            header = row
            continue
        if row[0] != "UNIT":
            continue
        rec = dict(zip(header, row))
        uid = rec["ID"].strip()
        units[uid] = {
            "type": rec.get("TYPE", "DEPOSIT"),
            "name": rec.get("NAME", ""),
            "description": rec.get("DESCRIPTION", ""),
            "layer": rec.get("LAYER", ""),
        }
        if rec.get("PARENT", "").strip():
            parent[uid] = rec["PARENT"].strip()
        for child in _split(rec.get("CHILDREN", "")):
            parent[child] = uid
        above += [(uid, x) for x in _split(rec.get("ABOVE", ""))]
        above += [(x, uid) for x in _split(rec.get("BELOW", ""))]
        contemporary += [(uid, x) for x in _split(rec.get("CONTEMPORARY", ""))]
        if rec.get("EARLIER", "").strip() or rec.get("LATER", "").strip():
            raise NotImplementedError(f"{p}: EARLIER/LATER relations (unit {uid!r}) are not supported yet")
    if not header:
        raise ValueError(f"{p} is not a Harris Matrix Composer CSV export")
    return _build(p, units, parent, above, contemporary)
