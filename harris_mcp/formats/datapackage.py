"""T. S. Dye's `hm` tables, as a Frictionless data package or an hm project.

The same CSV tables (https://github.com/tsdye/harris-matrix) are described
either by a Frictionless ``datapackage.json`` descriptor or by an hm
``.ini`` project file whose ``[Input files]`` section names each table
(``events`` and ``event-order`` there are ``radiocarbon`` and ``date-order``
here).

Accepted paths: the descriptor or ``.ini`` file, the directory that holds
one, or a ``.zip`` of either (the descriptor may sit in a subfolder).

Resource mapping (only ``contexts`` and ``observations`` are required):

    contexts      label -> id, unit-type -> type, period/phase ids resolved
                  to their labels via ``periods`` / ``phases``; the other
                  columns (position, url, ...) land in ``attrs``
    observations  younger, older       -> ``above`` (younger above older)
    inferences    first, second        -> ``equal`` (same unit)
    date-order    older, younger       -> ``above``, attrs.source="date-order"
                  (a chronological, not stratigraphic, ordering)
    radiocarbon   rows attached to their context as attrs["radiocarbon"]

Every relation keeps the resource it came from in ``attrs["source"]``.
Read-only: save as HMDP, CSV or XLSX.
"""

from __future__ import annotations

import configparser
import csv as _csv
import json
import tempfile
import zipfile
from pathlib import Path

from ..model import Context, Matrix, Relation
from ..registry import new_id

DESCRIPTOR = "datapackage.json"

# hm [Input files] keys -> resource names used here
_INI_ROLES = {"events": "radiocarbon", "event-order": "date-order"}
# Column names hm assumes when a table has no header row
_DEFAULT_FIELDS = {
    "contexts": ["label", "unit-type", "position", "period", "phase", "url"],
    "observations": ["younger", "older", "url"],
    "inferences": ["first", "second"],
    "date-order": ["older", "younger"],
    "periods": ["id", "label", "attribute", "url"],
    "phases": ["id", "label", "attribute", "url"],
    "radiocarbon": ["theta", "context", "lab", "association"],
}


def is_descriptor(path: Path) -> bool:
    """True if `path` is a Frictionless descriptor (not an HMDP file)."""
    if path.name == DESCRIPTOR:
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "resources" in data


def _read_ini(path: Path) -> configparser.ConfigParser | None:
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return None
    if not cp.has_section("Input files"):
        return None
    files = cp["Input files"]
    return cp if files.get("contexts") and files.get("observations") else None


def is_hm_dir(path: Path) -> bool:
    """True if `path` holds a datapackage.json or a usable hm .ini project."""
    return (path / DESCRIPTOR).exists() or any(_read_ini(i) for i in sorted(path.glob("*.ini")))


def _find_project(root: Path) -> Path:
    if root.is_file():
        return root
    for candidates in (sorted(root.rglob(DESCRIPTOR)), sorted(root.rglob("*.ini"))):
        for c in candidates:
            if c.name == DESCRIPTOR or _read_ini(c):
                return c
    raise FileNotFoundError(f"No {DESCRIPTOR} or hm .ini project found in {root}")


def _url(value: str) -> str:
    # hm writes org-mode links: [[http://...]]
    return value.strip().removeprefix("[[").removesuffix("]]")


def _resources(project: Path) -> tuple[str | None, dict[str, Path], set[str]]:
    """(name, resource name -> table path, resources lacking a header row)."""
    base = project.parent
    if project.suffix.lower() == ".ini":
        cp = _read_ini(project)
        if cp is None:
            raise ValueError(f"{project} has no [Input files] naming contexts and observations")
        paths = {_INI_ROLES.get(k, k): base / v for k, v in cp["Input files"].items() if v.strip()}
        headers = cp["Input file headers"] if cp.has_section("Input file headers") else {}
        no_header = {_INI_ROLES.get(k, k) for k, v in headers.items() if v.strip().lower() in ("no", "false", "off")}
        return project.stem, paths, no_header
    meta = json.loads(project.read_text(encoding="utf-8"))
    paths = {r["name"]: base / r["path"] for r in meta.get("resources", []) if "name" in r and "path" in r}
    return meta.get("name"), paths, set()


def _load_project(project: Path, source: Path) -> Matrix:
    name, paths, no_header = _resources(project)
    missing = [r for r in ("contexts", "observations") if r not in paths]
    if missing:
        raise ValueError(f"{project} lacks required resource(s): {', '.join(missing)}")

    def rows(name: str) -> list[dict[str, str]]:
        if name not in paths:
            return []
        fields = _DEFAULT_FIELDS.get(name) if name in no_header else None
        with paths[name].open(newline="", encoding="utf-8") as f:
            return list(_csv.DictReader(f, fieldnames=fields))

    periods = {r["id"]: r.get("label") or r["id"] for r in rows("periods")}
    phases = {r["id"]: r.get("label") or r["id"] for r in rows("phases")}
    c14: dict[str, list[dict]] = {}
    for r in rows("radiocarbon"):
        c14.setdefault(r["context"], []).append({k: v for k, v in r.items() if k != "context" and v})

    name = name or source.stem
    m = Matrix(id=new_id(hint=name), name=name, path=str(source))
    for r in rows("contexts"):
        ctx_id = r.get("label")
        if not ctx_id:
            continue
        attrs = {k: v for k, v in r.items() if k not in ("label", "unit-type", "period", "phase") and v != ""}
        if "url" in attrs:
            attrs["url"] = _url(attrs["url"])
        if ctx_id in c14:
            attrs["radiocarbon"] = c14[ctx_id]
        period, phase = r.get("period") or None, r.get("phase") or None
        m.add_context(Context(
            id=ctx_id,
            type=r.get("unit-type") or None,
            period=periods.get(period, period) if period else None,
            phase=phases.get(phase, phase) if phase else None,
            attrs=attrs,
        ))

    for r in rows("observations"):
        m.add_relation(Relation(a=r["younger"], b=r["older"], kind="above", attrs={"source": "observation"}))
    for r in rows("inferences"):
        m.add_relation(Relation(a=r["first"], b=r["second"], kind="equal", attrs={"source": "inference"}))
    for r in rows("date-order"):
        m.add_relation(Relation(a=r["younger"], b=r["older"], kind="above", attrs={"source": "date-order"}))
    if not m.contexts:
        raise ValueError(f"{project} contains no contexts")
    m.rebuild_indexes()
    return m


def load(path: str | Path) -> Matrix:
    p = Path(path)
    if p.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(p) as zf:
                zf.extractall(tmp)
            return _load_project(_find_project(Path(tmp)), p)
    return _load_project(_find_project(p), p)


def dump(matrix: Matrix, path: str | Path) -> None:
    raise NotImplementedError(
        "Writing Frictionless data packages is not supported; save as hmdp, csv or xlsx."
    )
