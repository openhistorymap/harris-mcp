"""Structural validation for a Harris matrix."""

from __future__ import annotations

import networkx as nx

from .model import Matrix


def validate(matrix: Matrix) -> dict:
    """Return a diagnostics report.

    Pure read; never mutates the matrix.
    """
    g = matrix.graph

    cycles: list[list[str]] = []
    try:
        cycles = [list(c) for c in nx.simple_cycles(g)]
    except Exception:  # extremely large graphs
        cycles = []

    # Dangling: referenced in a relation but missing from contexts
    declared = set(matrix.contexts.keys())
    referenced: set[str] = set()
    for r in matrix.relations:
        referenced.add(r.a)
        referenced.add(r.b)
    dangling = sorted(referenced - declared)

    # Redundant: edges that disappear under transitive reduction
    redundant: list[tuple[str, str]] = []
    if not cycles:
        try:
            tr = nx.transitive_reduction(g)
            redundant = sorted(set(g.edges) - set(tr.edges))
        except Exception:
            redundant = []

    # Orphans: nodes with no edges in or out, not part of any equivalence
    classes = matrix.equiv.classes()
    multi_class_members = {n for nodes in classes.values() if len(nodes) > 1 for n in nodes}
    orphans = sorted(
        node
        for node in g.nodes
        if g.in_degree(node) == 0 and g.out_degree(node) == 0 and node not in multi_class_members
    )

    return {
        "cycles": cycles,
        "dangling": dangling,
        "redundant_edges": redundant,
        "orphans": orphans,
        "n_contexts": len(matrix.contexts),
        "n_edges": g.number_of_edges(),
        "valid": not cycles and not dangling,
    }
