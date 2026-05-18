"""Core data model for a Harris matrix.

The matrix is held in memory as a directed acyclic graph of `above` edges
plus a union-find of equivalence classes (`contemporary`, `same as`).
Every other relation kind (`below`, `cuts`, `fills`, ...) is canonicalised
into one of these two structures at load time; the original verb is kept
in `Relation.attrs["original_kind"]` so round-trips preserve information.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Literal

import networkx as nx
from pydantic import BaseModel, Field

ContextKind = str
RelationKind = Literal[
    "above",
    "below",
    "equal",
    "contemporary",
    "cuts",
    "cut_by",
    "fills",
    "filled_by",
    "abuts",
]


class Context(BaseModel):
    """A stratigraphic unit (also: SU, context, locus)."""

    id: str
    type: ContextKind | None = None
    period: str | None = None
    phase: str | None = None
    group: str | None = None
    description: str | None = None
    geometry: dict | None = None  # GeoJSON if present
    attrs: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    a: str
    b: str
    kind: RelationKind
    attrs: dict[str, Any] = Field(default_factory=dict)


class Correspondence(BaseModel):
    """Cross-document assertion: ctx in matrix A corresponds to ctx in matrix B."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    matrix_a: str
    ctx_a: str
    matrix_b: str
    ctx_b: str
    kind: Literal["same_as", "contemporary_with"] = "same_as"
    note: str | None = None
    author: str = "llm"
    ts: float = Field(default_factory=time.time)


class ChangelogEntry(BaseModel):
    """One interpretive edit, in append-only order."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    op: str
    args: dict[str, Any]
    note: str | None = None
    author: str = "llm"
    ts: float = Field(default_factory=time.time)
    reverted: bool = False


# Canonicalisation: "below" reverses; cuts/fills/abuts imply `above`/`below`
# with the original verb preserved in attrs. Equivalences collapse into the
# union-find layer.
_REVERSE = {"below", "cut_by", "filled_by"}
_FORWARD = {"above", "cuts", "fills"}
_EQUIVALENCE = {"equal", "contemporary"}


class UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self._parent.setdefault(x, x)

    def find(self, x: str) -> str:
        self.add(x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def classes(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for node in self._parent:
            out.setdefault(self.find(node), []).append(node)
        return out


class Matrix:
    """In-memory mutable representation of one Harris matrix.

    `graph` holds canonical `above` edges (a above b → edge a→b).
    `equiv` is the equivalence union-find for `contemporary`/`equal`.
    """

    def __init__(self, *, id: str, name: str | None = None, path: str | None = None):
        self.id = id
        self.name = name or id
        self.path = path
        self.contexts: dict[str, Context] = {}
        self.relations: list[Relation] = []
        self.graph: nx.DiGraph = nx.DiGraph()
        self.equiv: UnionFind = UnionFind()
        self.phases: dict[str, list[str]] = {}
        self.periods: dict[str, list[str]] = {}
        self.changelog: list[ChangelogEntry] = []

    # --- bulk loaders (used by format adapters) -----------------------------

    def add_context(self, ctx: Context) -> None:
        self.contexts[ctx.id] = ctx
        self.graph.add_node(ctx.id)
        self.equiv.add(ctx.id)
        if ctx.phase:
            self.phases.setdefault(ctx.phase, []).append(ctx.id)
        if ctx.period:
            self.periods.setdefault(ctx.period, []).append(ctx.id)

    def add_relation(self, rel: Relation) -> None:
        """Canonicalise and store a relation."""
        self.relations.append(rel)
        kind = rel.kind
        a, b = rel.a, rel.b
        for node in (a, b):
            if node not in self.contexts:
                # Reference to a not-yet-loaded context: create a shell.
                self.add_context(Context(id=node))
        if kind in _FORWARD:
            self.graph.add_edge(a, b, kind=kind)
        elif kind in _REVERSE:
            self.graph.add_edge(b, a, kind=kind)
        elif kind in _EQUIVALENCE:
            self.equiv.union(a, b)
        elif kind == "abuts":
            # abuts has no temporal ordering; record as undirected attribute
            self.graph.add_node(a)
            self.graph.add_node(b)
        else:
            raise ValueError(f"Unknown relation kind: {kind!r}")

    # --- indexing rebuild ---------------------------------------------------

    def rebuild_indexes(self) -> None:
        self.phases.clear()
        self.periods.clear()
        for ctx in self.contexts.values():
            if ctx.phase:
                self.phases.setdefault(ctx.phase, []).append(ctx.id)
            if ctx.period:
                self.periods.setdefault(ctx.period, []).append(ctx.id)

    # --- changelog ----------------------------------------------------------

    def record(self, op: str, args: dict[str, Any], *, note: str | None = None, author: str = "llm") -> ChangelogEntry:
        entry = ChangelogEntry(op=op, args=args, note=note, author=author)
        self.changelog.append(entry)
        return entry

    # --- serialisation snapshot --------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "profile": "harris-matrix-data-package-v1",
            "contexts": [c.model_dump(exclude_none=True) for c in self.contexts.values()],
            "relations": [r.model_dump(exclude_none=True) for r in self.relations],
            "changelog": [e.model_dump() for e in self.changelog],
        }

    # --- iteration helpers --------------------------------------------------

    def iter_contexts(self) -> Iterable[Context]:
        return self.contexts.values()
