"""HMDP — Harris Matrix Data Package.

Lossless JSON pivot format. Every other adapter round-trips through this.

Top-level keys:
    name        str
    profile     str (always "harris-matrix-data-package-v1")
    contexts    list of Context dicts
    relations   list of Relation dicts (a, b, kind, attrs)
    changelog   optional list of ChangelogEntry dicts (provenance preserved
                across saves so an LLM's reasoning trail is not lost)
"""

from __future__ import annotations

import json
from pathlib import Path

from ..model import ChangelogEntry, Context, Matrix, Relation
from ..registry import new_id

PROFILE = "harris-matrix-data-package-v1"


def load(path: str | Path) -> Matrix:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    name = data.get("name") or p.stem
    m = Matrix(id=new_id(hint=p.stem), name=name, path=str(p))
    for raw in data.get("contexts", []):
        m.add_context(Context(**raw))
    for raw in data.get("relations", []):
        m.add_relation(Relation(**raw))
    for raw in data.get("changelog", []):
        try:
            m.changelog.append(ChangelogEntry(**raw))
        except Exception:
            # Tolerate slightly malformed legacy changelog entries
            continue
    m.rebuild_indexes()
    return m


def dump(matrix: Matrix, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = matrix.to_dict()
    payload["profile"] = PROFILE
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
