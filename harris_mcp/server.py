"""FastMCP server exposing the Harris matrix tool & resource surface.

The split:
    * Reading tools — high-density payloads tuned to how an LLM consumes context.
    * Writing tools — every mutation lands on a per-matrix changelog with a
      `note` so the human archaeologist can see why the LLM made the edit.
    * Corpus tools — operations across multiple loaded matrices, including
      cross-document correspondences.
    * Output tools — save / convert / render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import networkx as nx
from fastmcp import FastMCP
from pydantic import BaseModel

from . import formats, registry
from .model import Context, Correspondence, Matrix, Relation
from .render import render as render_matrix
from .validate import validate as validate_matrix

mcp = FastMCP(name="Harris Matrix MCP")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _ctx_summary(c: Context) -> dict:
    return c.model_dump(exclude_none=True)


def _matrix_summary(m: Matrix) -> dict:
    g = m.graph
    try:
        depth = len(list(nx.topological_generations(g)))
    except nx.NetworkXUnfeasible:
        depth = -1
    return {
        "id": m.id,
        "name": m.name,
        "path": m.path,
        "n_contexts": len(m.contexts),
        "n_edges": g.number_of_edges(),
        "n_phases": len(m.phases),
        "n_periods": len(m.periods),
        "depth": depth,
        "changelog_entries": len(m.changelog),
    }


# --------------------------------------------------------------------------- #
# Loading                                                                     #
# --------------------------------------------------------------------------- #


@mcp.tool
def open_matrix(path: str, fmt: str = "auto") -> dict:
    """Load a Harris matrix file and return its handle.

    `fmt` may be "auto" (detect from extension) or one of:
    hmdp, json, csv, xlsx, hmc, hmcx.
    """
    m = formats.load(path, fmt=fmt)
    registry.register(m)
    return {"matrix_id": m.id, **_matrix_summary(m), "diagnostics": validate_matrix(m)}


@mcp.tool
def open_corpus(paths: list[str], fmt: str = "auto") -> dict:
    """Load several matrix files at once. Useful for cross-document reasoning."""
    opened, failed = [], []
    for p in paths:
        try:
            m = formats.load(p, fmt=fmt)
            registry.register(m)
            opened.append(_matrix_summary(m))
        except Exception as exc:  # one bad file should not block the rest
            failed.append({"path": p, "error": str(exc)})
    return {"opened": opened, "failed": failed}


@mcp.tool
def close_matrix(matrix_id: str) -> dict:
    registry.close(matrix_id)
    return {"closed": matrix_id, "open_matrices": registry.list_ids()}


@mcp.tool
def list_open_matrices() -> list[dict]:
    return [_matrix_summary(m) for m in registry.all_matrices()]


# --------------------------------------------------------------------------- #
# Reading individual units                                                    #
# --------------------------------------------------------------------------- #


@mcp.tool
def get_context(matrix_id: str, ctx: str) -> dict:
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(f"No such context {ctx!r} in matrix {matrix_id!r}")
    return _ctx_summary(m.contexts[ctx])


@mcp.tool
def list_contexts(
    matrix_id: str,
    phase: Optional[str] = None,
    period: Optional[str] = None,
    type: Optional[str] = None,
    group: Optional[str] = None,
    has_geometry: Optional[bool] = None,
    limit: int = 200,
) -> list[dict]:
    m = registry.get(matrix_id)
    out: list[dict] = []
    for c in m.contexts.values():
        if phase is not None and c.phase != phase:
            continue
        if period is not None and c.period != period:
            continue
        if type is not None and c.type != type:
            continue
        if group is not None and c.group != group:
            continue
        if has_geometry is True and not c.geometry:
            continue
        if has_geometry is False and c.geometry:
            continue
        out.append(_ctx_summary(c))
        if len(out) >= limit:
            break
    return out


@mcp.tool
def count_contexts(matrix_id: str, group_by: Literal["phase", "period", "type", "group"] = "phase") -> dict:
    m = registry.get(matrix_id)
    counts: dict[str, int] = {}
    for c in m.contexts.values():
        key = getattr(c, group_by) or "<none>"
        counts[key] = counts.get(key, 0) + 1
    return counts


@mcp.tool
def search_contexts(matrix_id: str, query: str, limit: int = 50) -> list[dict]:
    """Substring (case-insensitive) match across id, description, and attrs."""
    m = registry.get(matrix_id)
    q = query.lower()
    out = []
    for c in m.contexts.values():
        hay = " ".join(
            [c.id, c.description or ""] + [str(v) for v in c.attrs.values()]
        ).lower()
        if q in hay:
            out.append(_ctx_summary(c))
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- #
# Reading relationships                                                       #
# --------------------------------------------------------------------------- #


@mcp.tool
def neighbors(
    matrix_id: str,
    ctx: str,
    direction: Literal["above", "below", "contemporary", "any"] = "any",
    depth: int = 1,
) -> dict:
    m = registry.get(matrix_id)
    g = m.graph
    if ctx not in g:
        raise KeyError(ctx)
    result: dict[str, list[str]] = {"above": [], "below": [], "contemporary": []}
    if direction in ("above", "any"):
        nodes = nx.single_source_shortest_path_length(g, ctx, cutoff=depth)
        result["above"] = sorted(n for n in nodes if n != ctx)
    if direction in ("below", "any"):
        nodes = nx.single_source_shortest_path_length(g.reverse(copy=False), ctx, cutoff=depth)
        result["below"] = sorted(n for n in nodes if n != ctx)
    if direction in ("contemporary", "any"):
        root = m.equiv.find(ctx)
        klass = m.equiv.classes().get(root, [])
        result["contemporary"] = sorted(n for n in klass if n != ctx)
    return result


@mcp.tool
def ancestors(matrix_id: str, ctx: str) -> list[str]:
    """All units stratigraphically earlier than `ctx` (transitive)."""
    m = registry.get(matrix_id)
    return sorted(nx.ancestors(m.graph, ctx))


@mcp.tool
def descendants(matrix_id: str, ctx: str) -> list[str]:
    """All units stratigraphically later than `ctx` (transitive)."""
    m = registry.get(matrix_id)
    return sorted(nx.descendants(m.graph, ctx))


@mcp.tool
def relation(matrix_id: str, a: str, b: str) -> str:
    """Return the stratigraphic relationship between `a` and `b`.

    One of: "above", "below", "equal", "unordered".
    """
    m = registry.get(matrix_id)
    if m.equiv.find(a) == m.equiv.find(b) and a != b:
        return "equal"
    if nx.has_path(m.graph, a, b):
        return "above"
    if nx.has_path(m.graph, b, a):
        return "below"
    return "unordered"


@mcp.tool
def path(matrix_id: str, a: str, b: str) -> Optional[list[str]]:
    """Shortest stratigraphic path from `a` to `b`, or null if unordered."""
    m = registry.get(matrix_id)
    try:
        return nx.shortest_path(m.graph, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


@mcp.tool
def between(matrix_id: str, earlier: str, later: str) -> list[str]:
    """Units strictly between two contexts on the partial order."""
    m = registry.get(matrix_id)
    if not nx.has_path(m.graph, earlier, later):
        return []
    desc = set(nx.descendants(m.graph, earlier))
    anc = set(nx.ancestors(m.graph, later))
    return sorted((desc & anc) - {earlier, later})


@mcp.tool
def contemporaries(matrix_id: str, ctx: str) -> list[str]:
    m = registry.get(matrix_id)
    root = m.equiv.find(ctx)
    return sorted(n for n in m.equiv.classes().get(root, []) if n != ctx)


# --------------------------------------------------------------------------- #
# Whole-matrix views                                                          #
# --------------------------------------------------------------------------- #


@mcp.tool
def topological_layers(matrix_id: str) -> list[list[str]]:
    """The Harris layout: contexts grouped by topological generation,
    earliest first."""
    m = registry.get(matrix_id)
    try:
        # Edges point from the later unit down to the earlier one, so
        # topological generations come out latest first.
        return [sorted(layer) for layer in reversed(list(nx.topological_generations(m.graph)))]
    except nx.NetworkXUnfeasible:
        return []


@mcp.tool
def phases(matrix_id: str) -> dict:
    m = registry.get(matrix_id)
    return {p: sorted(members) for p, members in m.phases.items()}


@mcp.tool
def periods(matrix_id: str) -> dict:
    m = registry.get(matrix_id)
    return {p: sorted(members) for p, members in m.periods.items()}


@mcp.tool
def phase_contexts(matrix_id: str, phase: str) -> list[str]:
    m = registry.get(matrix_id)
    members = set(m.phases.get(phase, []))
    if not members:
        return []
    sub = m.graph.subgraph(members)
    try:
        return list(nx.topological_sort(sub))
    except nx.NetworkXUnfeasible:
        return sorted(members)


@mcp.tool
def validate(matrix_id: str) -> dict:
    return validate_matrix(registry.get(matrix_id))


@mcp.tool
def summary(matrix_id: str) -> dict:
    return _matrix_summary(registry.get(matrix_id))


def _phase_graph(m: Matrix) -> nx.DiGraph:
    """Phase-level graph: an edge p -> q when some unit of p lies above a unit of q."""
    pg = nx.DiGraph()
    pg.add_nodes_from(m.phases)
    for a, b in m.graph.edges:
        pa = (m.contexts.get(a) or Context(id=a)).phase
        pb = (m.contexts.get(b) or Context(id=b)).phase
        if pa and pb and pa != pb:
            pg.add_edge(pa, pb)
    return pg


@mcp.tool
def phase_sequence(matrix_id: str) -> dict:
    """Phase order implied by the stratigraphy, earliest first.

    `conflicts` lists groups of phases that each lie above one another and
    so cannot be ordered; they appear together as one step of `sequence`.
    """
    m = registry.get(matrix_id)
    cond = nx.condensation(_phase_graph(m))
    sequence = [sorted(cond.nodes[n]["members"]) for n in reversed(list(nx.topological_sort(cond)))]
    return {"sequence": sequence, "conflicts": [step for step in sequence if len(step) > 1]}


@mcp.tool
def anomalies(matrix_id: str, phase_order: Optional[list[str]] = None) -> list[dict]:
    """Phase assignments that violate the stratigraphic partial order.

    With `phase_order` (phase names, earliest first) returns pairs (a, b)
    where `a` is stratigraphically above `b` but `a`'s phase is earlier.
    Without it the order is inferred from the matrix itself (see
    `phase_sequence`), and pairs are returned where the two phases each lie
    above the other, so no consistent order exists.
    """
    m = registry.get(matrix_id)
    out = []
    if phase_order:
        rank = {p: i for i, p in enumerate(phase_order)}
        in_conflict = lambda pa, pb: pa in rank and pb in rank and rank[pa] < rank[pb]
        issue = "a is above b but a's phase is earlier in phase_order"
    else:
        component = {}
        for i, members in enumerate(nx.strongly_connected_components(_phase_graph(m))):
            for p in members:
                component[p] = i
        in_conflict = lambda pa, pb: component[pa] == component[pb]
        issue = "a is above b but the phases are also ordered the other way elsewhere"
    for a, b in m.graph.edges:
        pa = (m.contexts.get(a) or Context(id=a)).phase
        pb = (m.contexts.get(b) or Context(id=b)).phase
        if pa and pb and pa != pb and in_conflict(pa, pb):
            out.append({"a": a, "b": b, "phase_a": pa, "phase_b": pb, "issue": issue})
    return out


@mcp.tool
def describe_context(matrix_id: str, ctx: str, neighborhood: int = 2) -> dict:
    """High-density read: context + neighborhood + phase + correspondences."""
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(ctx)
    base = _ctx_summary(m.contexts[ctx])
    nb = neighbors(matrix_id=matrix_id, ctx=ctx, direction="any", depth=neighborhood)
    corr = [c.model_dump() for c in registry.correspondences(matrix_id, ctx)]
    return {
        "context": base,
        "neighborhood": nb,
        "ancestors": ancestors(matrix_id=matrix_id, ctx=ctx),
        "descendants": descendants(matrix_id=matrix_id, ctx=ctx),
        "phase_members": sorted(m.phases.get(base.get("phase") or "", [])),
        "correspondences": corr,
    }


@mcp.tool
def describe_phase(matrix_id: str, phase: str) -> dict:
    m = registry.get(matrix_id)
    members = m.phases.get(phase, [])
    boundary_above: set[str] = set()
    boundary_below: set[str] = set()
    member_set = set(members)
    for n in members:
        for succ in m.graph.successors(n):
            if succ not in member_set:
                boundary_below.add(succ)
        for pred in m.graph.predecessors(n):
            if pred not in member_set:
                boundary_above.add(pred)
    return {
        "phase": phase,
        "members": sorted(members),
        "boundary_above": sorted(boundary_above),
        "boundary_below": sorted(boundary_below),
        "anomalies": [a for a in anomalies(matrix_id=matrix_id) if a["phase_a"] == phase or a["phase_b"] == phase],
    }


@mcp.tool
def boundary_contexts(matrix_id: str, phase: str) -> dict:
    """Contexts in `phase` that touch units outside the phase."""
    return {
        k: v for k, v in describe_phase(matrix_id=matrix_id, phase=phase).items()
        if k in ("boundary_above", "boundary_below")
    }


# --------------------------------------------------------------------------- #
# Writing (interpretation, all changelogged)                                  #
# --------------------------------------------------------------------------- #


class ContextPatch(BaseModel):
    type: Optional[str] = None
    period: Optional[str] = None
    phase: Optional[str] = None
    group: Optional[str] = None
    description: Optional[str] = None
    geometry: Optional[dict] = None
    attrs: Optional[dict] = None


@mcp.tool
def add_context(matrix_id: str, ctx: dict, note: Optional[str] = None, author: str = "llm") -> dict:
    m = registry.get(matrix_id)
    c = Context(**ctx)
    if c.id in m.contexts:
        raise ValueError(f"Context {c.id!r} already exists")
    m.add_context(c)
    entry = m.record("add_context", {"ctx": c.model_dump(exclude_none=True)}, note=note, author=author)
    return {"context": _ctx_summary(c), "changelog_id": entry.id}


@mcp.tool
def update_context(matrix_id: str, ctx: str, patch: dict, note: Optional[str] = None, author: str = "llm") -> dict:
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(ctx)
    current = m.contexts[ctx]
    updates = ContextPatch(**patch).model_dump(exclude_none=True)
    before = current.model_dump()
    for k, v in updates.items():
        if k == "attrs":
            current.attrs.update(v)
        else:
            setattr(current, k, v)
    m.rebuild_indexes()
    entry = m.record("update_context", {"ctx": ctx, "patch": updates, "before": before}, note=note, author=author)
    return {"context": _ctx_summary(current), "changelog_id": entry.id}


@mcp.tool
def delete_context(matrix_id: str, ctx: str, note: Optional[str] = None, author: str = "llm") -> dict:
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(ctx)
    before = m.contexts[ctx].model_dump()
    related = [r.model_dump() for r in m.relations if r.a == ctx or r.b == ctx]
    m.relations = [r for r in m.relations if r.a != ctx and r.b != ctx]
    m.graph.remove_node(ctx)
    m.contexts.pop(ctx)
    m.rebuild_indexes()
    entry = m.record("delete_context", {"ctx": ctx, "before": before, "relations": related}, note=note, author=author)
    return {"deleted": ctx, "changelog_id": entry.id, "removed_relations": len(related)}


@mcp.tool
def add_relation(matrix_id: str, a: str, b: str, kind: str = "above",
                 note: Optional[str] = None, author: str = "llm") -> dict:
    m = registry.get(matrix_id)
    rel = Relation(a=a, b=b, kind=kind)
    m.add_relation(rel)
    entry = m.record("add_relation", {"a": a, "b": b, "kind": kind}, note=note, author=author)
    return {"relation": rel.model_dump(), "changelog_id": entry.id}


@mcp.tool
def remove_relation(matrix_id: str, a: str, b: str, kind: Optional[str] = None,
                    note: Optional[str] = None, author: str = "llm") -> dict:
    m = registry.get(matrix_id)
    before = len(m.relations)
    m.relations = [
        r for r in m.relations
        if not (r.a == a and r.b == b and (kind is None or r.kind == kind))
    ]
    removed = before - len(m.relations)
    if m.graph.has_edge(a, b):
        m.graph.remove_edge(a, b)
    if m.graph.has_edge(b, a):
        m.graph.remove_edge(b, a)
    entry = m.record("remove_relation", {"a": a, "b": b, "kind": kind, "removed": removed}, note=note, author=author)
    return {"removed": removed, "changelog_id": entry.id}


@mcp.tool
def assign_phase(matrix_id: str, ctx: str, phase: str,
                 note: Optional[str] = None, author: str = "llm") -> dict:
    return update_context(matrix_id=matrix_id, ctx=ctx, patch={"phase": phase}, note=note, author=author)


@mcp.tool
def mark_contemporary(matrix_id: str, a: str, b: str,
                      note: Optional[str] = None, author: str = "llm") -> dict:
    return add_relation(matrix_id=matrix_id, a=a, b=b, kind="contemporary", note=note, author=author)


@mcp.tool
def attach_note(matrix_id: str, ctx: str, note: str, author: str = "llm") -> dict:
    """Append a free-form interpretive note to a context's `attrs.notes` list."""
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(ctx)
    notes = m.contexts[ctx].attrs.setdefault("notes", [])
    notes.append({"text": note, "author": author})
    entry = m.record("attach_note", {"ctx": ctx, "note": note}, note=note, author=author)
    return {"context": _ctx_summary(m.contexts[ctx]), "changelog_id": entry.id}


# --------------------------------------------------------------------------- #
# Provenance                                                                  #
# --------------------------------------------------------------------------- #


@mcp.tool
def history(matrix_id: str, limit: int = 100) -> list[dict]:
    m = registry.get(matrix_id)
    return [e.model_dump() for e in m.changelog[-limit:]]


@mcp.tool
def revert(matrix_id: str, changelog_id: str) -> dict:
    """Mark a changelog entry as reverted and undo its effect.

    Best-effort: handles add_context, add_relation, attach_note, and
    update_context (restores the recorded `before` snapshot). For
    delete_context, restores the unit but not its incident relations beyond
    what was captured.
    """
    m = registry.get(matrix_id)
    target = next((e for e in m.changelog if e.id == changelog_id), None)
    if target is None:
        raise KeyError(changelog_id)
    if target.reverted:
        return {"changelog_id": changelog_id, "already_reverted": True}

    op, args = target.op, target.args
    if op == "add_context":
        cid = args["ctx"]["id"]
        if cid in m.contexts:
            m.relations = [r for r in m.relations if r.a != cid and r.b != cid]
            if cid in m.graph:
                m.graph.remove_node(cid)
            m.contexts.pop(cid, None)
    elif op == "add_relation":
        m.relations = [
            r for r in m.relations
            if not (r.a == args["a"] and r.b == args["b"] and r.kind == args["kind"])
        ]
        if m.graph.has_edge(args["a"], args["b"]):
            m.graph.remove_edge(args["a"], args["b"])
        if m.graph.has_edge(args["b"], args["a"]):
            m.graph.remove_edge(args["b"], args["a"])
    elif op == "update_context":
        before = args.get("before") or {}
        cid = args["ctx"]
        if cid in m.contexts:
            m.contexts[cid] = Context(**before)
    elif op == "delete_context":
        before = args.get("before") or {}
        if before:
            m.add_context(Context(**before))
        for rel in args.get("relations", []):
            m.add_relation(Relation(**rel))
    elif op == "attach_note":
        cid = args["ctx"]
        notes = m.contexts.get(cid, Context(id=cid)).attrs.get("notes", [])
        if notes:
            notes.pop()
    else:
        return {"changelog_id": changelog_id, "error": f"revert not implemented for op {op!r}"}

    target.reverted = True
    m.rebuild_indexes()
    return {"changelog_id": changelog_id, "reverted": True}


@mcp.tool
def diff(matrix_id: str, from_step: Optional[str] = None, to_step: Optional[str] = None) -> list[dict]:
    """Return the changelog slice between two entry ids (inclusive)."""
    m = registry.get(matrix_id)
    if from_step is None and to_step is None:
        return [e.model_dump() for e in m.changelog]
    started = from_step is None
    out: list[dict] = []
    for e in m.changelog:
        if not started and e.id == from_step:
            started = True
        if started:
            out.append(e.model_dump())
        if to_step is not None and e.id == to_step:
            break
    return out


# --------------------------------------------------------------------------- #
# Cross-document                                                              #
# --------------------------------------------------------------------------- #


@mcp.tool
def query_corpus(
    phase: Optional[str] = None,
    period: Optional[str] = None,
    type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Search across every open matrix. Returns (matrix_id, context) pairs."""
    out = []
    for m in registry.all_matrices():
        for c in m.contexts.values():
            if phase is not None and c.phase != phase:
                continue
            if period is not None and c.period != period:
                continue
            if type is not None and c.type != type:
                continue
            if query is not None:
                hay = " ".join(
                    [c.id, c.description or ""] + [str(v) for v in c.attrs.values()]
                ).lower()
                if query.lower() not in hay:
                    continue
            out.append({"matrix_id": m.id, "context": _ctx_summary(c)})
            if len(out) >= limit:
                return out
    return out


def _similarity(a: str, b: str) -> float:
    """Cheap normalised token Jaccard. Good enough for triage."""
    sa = {t for t in a.lower().split() if t}
    sb = {t for t in b.lower().split() if t}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@mcp.tool
def cross_reference(
    matrix_a: str,
    matrix_b: str,
    by: Literal["id", "description", "attrs"] = "description",
    threshold: float = 0.4,
    limit: int = 100,
) -> list[dict]:
    """Suggest candidate matches between two matrices. For LLM triage —
    nothing is asserted; nothing is written. Use `assert_correspondence`
    to record a conclusion."""
    a, b = registry.get(matrix_a), registry.get(matrix_b)
    out = []
    for ca in a.contexts.values():
        for cb in b.contexts.values():
            score = 0.0
            reason = ""
            if by == "id":
                score = 1.0 if ca.id == cb.id else 0.0
                reason = "identical id"
            elif by == "description":
                score = _similarity(ca.description or "", cb.description or "")
                reason = "description token overlap"
            elif by == "attrs":
                a_str = " ".join(str(v) for v in ca.attrs.values())
                b_str = " ".join(str(v) for v in cb.attrs.values())
                score = _similarity(a_str, b_str)
                reason = "attribute token overlap"
            if score >= threshold:
                out.append({
                    "ctx_a": ca.id, "ctx_b": cb.id,
                    "score": round(score, 3), "reason": reason,
                })
            if len(out) >= limit:
                return sorted(out, key=lambda x: -x["score"])
    return sorted(out, key=lambda x: -x["score"])


@mcp.tool
def assert_correspondence(
    matrix_a: str, ctx_a: str,
    matrix_b: str, ctx_b: str,
    kind: Literal["same_as", "contemporary_with"] = "same_as",
    note: Optional[str] = None, author: str = "llm",
) -> dict:
    """Record a cross-document correspondence — the LLM's interpretive
    conclusion. Stored outside the source matrices so round-trips to
    HMC/CSV do not erode it."""
    registry.get(matrix_a)  # validate
    registry.get(matrix_b)
    c = Correspondence(
        matrix_a=matrix_a, ctx_a=ctx_a,
        matrix_b=matrix_b, ctx_b=ctx_b,
        kind=kind, note=note, author=author,
    )
    registry.add_correspondence(c)
    return c.model_dump()


@mcp.tool
def correspondences(matrix_id: Optional[str] = None, ctx: Optional[str] = None) -> list[dict]:
    return [c.model_dump() for c in registry.correspondences(matrix_id, ctx)]


@mcp.tool
def compare_phases(matrix_a: str, matrix_b: str) -> dict:
    a, b = registry.get(matrix_a), registry.get(matrix_b)
    pa, pb = set(a.phases), set(b.phases)
    return {
        "only_in_a": sorted(pa - pb),
        "only_in_b": sorted(pb - pa),
        "shared": sorted(pa & pb),
        "sizes_a": {k: len(v) for k, v in a.phases.items()},
        "sizes_b": {k: len(v) for k, v in b.phases.items()},
    }


@mcp.tool
def compare_periods(matrix_a: str, matrix_b: str) -> dict:
    a, b = registry.get(matrix_a), registry.get(matrix_b)
    pa, pb = set(a.periods), set(b.periods)
    return {
        "only_in_a": sorted(pa - pb),
        "only_in_b": sorted(pb - pa),
        "shared": sorted(pa & pb),
    }


# --------------------------------------------------------------------------- #
# Output                                                                      #
# --------------------------------------------------------------------------- #


@mcp.tool
def save_matrix(matrix_id: str, path: str, fmt: str = "auto") -> dict:
    m = registry.get(matrix_id)
    formats.dump(m, path, fmt=fmt)
    return {"matrix_id": matrix_id, "path": str(path), "fmt": fmt}


@mcp.tool
def render(matrix_id: str, fmt: Literal["svg", "png", "dot"] = "svg",
           highlight: Optional[list[str]] = None) -> dict:
    """Render the matrix. Returns base64 for binary formats; text for dot."""
    import base64
    m = registry.get(matrix_id)
    data = render_matrix(m, fmt=fmt, highlight=highlight or [])
    if fmt == "dot":
        return {"format": "dot", "content": data.decode("utf-8")}
    return {"format": fmt, "base64": base64.b64encode(data).decode("ascii")}


@mcp.tool
def subgraph(matrix_id: str, roots: list[str],
             direction: Literal["up", "down", "both"] = "both",
             depth: int = 3) -> dict:
    """Local stratigraphy around `roots`, as an HMDP-shaped subset."""
    m = registry.get(matrix_id)
    keep: set[str] = set()
    for r in roots:
        keep.add(r)
        if direction in ("up", "both"):
            seen = nx.single_source_shortest_path_length(m.graph.reverse(copy=False), r, cutoff=depth)
            keep.update(seen)
        if direction in ("down", "both"):
            seen = nx.single_source_shortest_path_length(m.graph, r, cutoff=depth)
            keep.update(seen)
    contexts = [_ctx_summary(c) for c in m.contexts.values() if c.id in keep]
    relations = [r.model_dump() for r in m.relations if r.a in keep and r.b in keep]
    return {
        "name": f"{m.name}-subgraph",
        "profile": "harris-matrix-data-package-v1",
        "contexts": contexts,
        "relations": relations,
    }


@mcp.tool
def export_geojson(matrix_id: str) -> dict:
    """FeatureCollection of contexts that carry geometry. Suitable for
    handoff to ohm_importer."""
    m = registry.get(matrix_id)
    features = []
    for c in m.contexts.values():
        if not c.geometry:
            continue
        features.append({
            "type": "Feature",
            "geometry": c.geometry,
            "properties": {
                "id": c.id,
                "type": c.type,
                "period": c.period,
                "phase": c.phase,
                "group": c.group,
                "description": c.description,
                **{f"attr_{k}": v for k, v in c.attrs.items()},
            },
        })
    return {"type": "FeatureCollection", "features": features}


@mcp.tool
def link_ohm_feature(matrix_id: str, ctx: str, ohm_id: str,
                     note: Optional[str] = None, author: str = "llm") -> dict:
    """Record a cross-reference from a stratigraphic context to an Open
    History Map feature id. Stored on the context's attrs."""
    m = registry.get(matrix_id)
    if ctx not in m.contexts:
        raise KeyError(ctx)
    refs = m.contexts[ctx].attrs.setdefault("ohm_refs", [])
    refs.append(ohm_id)
    entry = m.record("link_ohm_feature", {"ctx": ctx, "ohm_id": ohm_id}, note=note, author=author)
    return {"context": _ctx_summary(m.contexts[ctx]), "changelog_id": entry.id}


# --------------------------------------------------------------------------- #
# Resources (cheap reads addressable as URIs)                                 #
# --------------------------------------------------------------------------- #


@mcp.resource("harris://matrices")
def res_matrices() -> list[dict]:
    return [_matrix_summary(m) for m in registry.all_matrices()]


@mcp.resource("harris://matrix/{matrix_id}/summary")
def res_summary(matrix_id: str) -> dict:
    return _matrix_summary(registry.get(matrix_id))


@mcp.resource("harris://matrix/{matrix_id}/context/{ctx}")
def res_context(matrix_id: str, ctx: str) -> dict:
    return _ctx_summary(registry.get(matrix_id).contexts[ctx])


@mcp.resource("harris://matrix/{matrix_id}/context/{ctx}/describe")
def res_describe(matrix_id: str, ctx: str) -> dict:
    return describe_context(matrix_id=matrix_id, ctx=ctx)


@mcp.resource("harris://matrix/{matrix_id}/layers")
def res_layers(matrix_id: str) -> list[list[str]]:
    return topological_layers(matrix_id=matrix_id)


@mcp.resource("harris://matrix/{matrix_id}/diagnostics")
def res_diagnostics(matrix_id: str) -> dict:
    return validate_matrix(registry.get(matrix_id))


@mcp.resource("harris://corpus/correspondences")
def res_correspondences() -> list[dict]:
    return [c.model_dump() for c in registry.correspondences()]
