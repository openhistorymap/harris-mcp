"""CSV adapter.

Two conventions are supported on read:

1. **Paired tables.** A directory containing `contexts.csv` and
   `relations.csv`, or two explicit paths joined by `+`
   (e.g. ``"site/contexts.csv+site/relations.csv"``).
2. **Edge list.** A single CSV whose first row is a header containing the
   columns ``above`` and ``below`` (any order). Contexts are inferred from
   the union of cells.

Write always produces paired tables; the path argument is treated as a
directory and the two files are written inside it.
"""

from __future__ import annotations

import csv as _csv
from pathlib import Path
from typing import Iterable

from ..model import Context, Matrix, Relation
from ..registry import new_id


def _read_rows(p: Path) -> list[dict[str, str]]:
    with p.open(newline="", encoding="utf-8") as f:
        return list(_csv.DictReader(f))


def _load_paired(contexts_path: Path, relations_path: Path, name: str) -> Matrix:
    m = Matrix(id=new_id(hint=name), name=name, path=str(contexts_path.parent))
    for row in _read_rows(contexts_path):
        ctx_id = row.pop("id", None) or row.pop("ID", None)
        if not ctx_id:
            continue
        known = {"type", "period", "phase", "group", "description"}
        kwargs = {k: v for k, v in row.items() if k in known and v != ""}
        extras = {k: v for k, v in row.items() if k not in known and v != ""}
        m.add_context(Context(id=ctx_id, attrs=extras, **kwargs))
    for row in _read_rows(relations_path):
        a = row.get("a") or row.get("from") or row.get("source")
        b = row.get("b") or row.get("to") or row.get("target")
        kind = row.get("kind") or row.get("relation") or "above"
        if not (a and b):
            continue
        m.add_relation(Relation(a=a, b=b, kind=kind))
    m.rebuild_indexes()
    return m


def _load_edge_list(path: Path) -> Matrix:
    m = Matrix(id=new_id(hint=path.stem), name=path.stem, path=str(path))
    for row in _read_rows(path):
        above = row.get("above")
        below = row.get("below")
        if not (above and below):
            continue
        m.add_relation(Relation(a=above, b=below, kind="above"))
    # contexts are auto-shelled by add_relation
    m.rebuild_indexes()
    return m


def load(path: str | Path) -> Matrix:
    if isinstance(path, str) and "+" in path:
        a, b = path.split("+", 1)
        return _load_paired(Path(a), Path(b), Path(a).stem)
    p = Path(path)
    if p.is_dir():
        contexts = p / "contexts.csv"
        relations = p / "relations.csv"
        if not (contexts.exists() and relations.exists()):
            raise FileNotFoundError(
                f"Expected contexts.csv + relations.csv inside {p}"
            )
        return _load_paired(contexts, relations, p.name)
    # Single CSV — sniff the header
    with p.open(newline="", encoding="utf-8") as f:
        reader = _csv.reader(f)
        header = next(reader, [])
    headers = {h.strip().lower() for h in header}
    if {"above", "below"} <= headers:
        return _load_edge_list(p)
    raise ValueError(
        f"{p} does not look like an edge list (need columns 'above','below'); "
        "for paired tables pass the directory containing contexts.csv + relations.csv"
    )


def dump(matrix: Matrix, path: str | Path) -> None:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    ctx_fields = ["id", "type", "period", "phase", "group", "description"]
    extra_keys: list[str] = []
    for c in matrix.contexts.values():
        for k in c.attrs:
            if k not in extra_keys:
                extra_keys.append(k)
    with (out / "contexts.csv").open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=ctx_fields + extra_keys)
        w.writeheader()
        for c in matrix.contexts.values():
            row = {k: getattr(c, k) or "" for k in ctx_fields}
            row.update({k: c.attrs.get(k, "") for k in extra_keys})
            w.writerow(row)
    with (out / "relations.csv").open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["a", "b", "kind"])
        w.writeheader()
        for r in matrix.relations:
            w.writerow({"a": r.a, "b": r.b, "kind": r.kind})
