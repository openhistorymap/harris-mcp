"""Cross-document unit reconciliation.

Deterministic support for deciding which units in two matrices are the same
unit recorded twice. Three layers, each usable on its own:

1. `candidates` — lexical similarity (description / attrs / id), optionally
   restricted to pairs with the same period and/or type.
2. `propose` — a 1:1 matching: greedy by score, where the score adds
   *structural agreement* (how many already-matched neighbours sit on the
   same side, above or below) to the text score, refined over a few rounds;
   pairs whose merge would put a unit both above and below another are
   rejected.
3. `contradictions` — given asserted `same_as` correspondences, the groups
   of units that end up in a stratigraphic cycle once the matrices are
   merged.

`sim/reconcile_sim.py` measures these against a known ground truth.
"""

from __future__ import annotations

from typing import Iterable, Literal

import networkx as nx

from .model import Matrix

Node = tuple[str, str]  # (matrix id, context id)


def similarity(a: str, b: str) -> float:
    """Normalised token Jaccard."""
    sa = {t for t in a.lower().split() if t}
    sb = {t for t in b.lower().split() if t}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def candidates(
    a: Matrix,
    b: Matrix,
    by: Literal["id", "description", "attrs"] = "description",
    threshold: float = 0.4,
    same_period: bool = False,
    same_type: bool = False,
) -> dict[tuple[str, str], float]:
    """(ctx_a, ctx_b) -> lexical score, for pairs scoring >= threshold."""
    out = {}
    for ca in a.contexts.values():
        for cb in b.contexts.values():
            if same_period and ca.period != cb.period:
                continue
            if same_type and ca.type != cb.type:
                continue
            if by == "id":
                score = 1.0 if ca.id == cb.id else 0.0
            elif by == "description":
                score = similarity(ca.description or "", cb.description or "")
            else:
                score = similarity(" ".join(str(v) for v in ca.attrs.values()),
                                   " ".join(str(v) for v in cb.attrs.values()))
            if score >= threshold:
                out[(ca.id, cb.id)] = score
    return out


class Merged:
    """The union of several matrices' `above` graphs, with units contracted
    as they are declared the same."""

    def __init__(self, matrices: Iterable[Matrix]):
        self.g = nx.DiGraph()
        for m in matrices:
            self.g.add_nodes_from((m.id, c) for c in m.graph.nodes)
            self.g.add_edges_from(((m.id, x), (m.id, y)) for x, y in m.graph.edges)
        self._rep: dict[Node, Node] = {n: n for n in self.g.nodes}
        self.members: dict[Node, set[Node]] = {n: {n} for n in self.g.nodes}

    def find(self, n: Node) -> Node:
        while self._rep[n] != n:
            n = self._rep[n]
        return n

    def would_cycle(self, x: Node, y: Node) -> bool:
        rx, ry = self.find(x), self.find(y)
        return rx != ry and (nx.has_path(self.g, rx, ry) or nx.has_path(self.g, ry, rx))

    def merge(self, x: Node, y: Node) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        nx.contracted_nodes(self.g, rx, ry, self_loops=False, copy=False)
        self._rep[ry] = rx
        self.members[rx] |= self.members.pop(ry)

    def cycles(self) -> list[set[Node]]:
        """Groups of original units caught in a cycle (each a set of nodes)."""
        return [
            set().union(*(self.members[n] for n in comp))
            for comp in nx.strongly_connected_components(self.g)
            if len(comp) > 1
        ]


def _greedy(scored: list[tuple[float, str, str]], merged: Merged | None, ida: str, idb: str):
    used_a, used_b, matched, rejected = set(), set(), {}, []
    for score, x, y in sorted(scored, reverse=True):
        if x in used_a or y in used_b:
            continue
        if merged is not None:
            if merged.would_cycle((ida, x), (idb, y)):
                rejected.append((x, y))
                continue
            merged.merge((ida, x), (idb, y))
        used_a.add(x)
        used_b.add(y)
        matched[x] = (y, score)
    return matched, rejected


def propose(
    a: Matrix,
    b: Matrix,
    text: dict[tuple[str, str], float],
    structure_weight: float = 0.5,
    rounds: int = 3,
    check_cycles: bool = True,
) -> dict:
    """A 1:1 matching between `a` and `b` from lexical scores `text`.

    With `structure_weight` 0 and `check_cycles` False this is plain greedy
    text matching. Returns matches (with their text score and structural
    agreement) and the pairs rejected because they would create a cycle.
    """
    ga, gb = a.graph, b.graph

    def agreement(x: str, y: str, m: dict[str, str]) -> float:
        agree = sum(1 for n in ga.predecessors(x) if m.get(n) in gb.pred[y]) + \
                sum(1 for n in ga.successors(x) if m.get(n) in gb.succ[y])
        deg = min(ga.degree(x), gb.degree(y))
        return agree / deg if deg else 0.0

    def run(score_of) -> tuple[dict, list]:
        merged = Merged([a, b]) if check_cycles else None
        return _greedy([(score_of(x, y, s), x, y) for (x, y), s in text.items()], merged, a.id, b.id)

    matched, rejected = run(lambda x, y, s: s)
    if structure_weight:
        for _ in range(rounds):
            current = {x: y for x, (y, _) in matched.items()}
            matched, rejected = run(lambda x, y, s: s + structure_weight * agreement(x, y, current))
    current = {x: y for x, (y, _) in matched.items()}
    return {
        "matches": [
            {"ctx_a": x, "ctx_b": y, "text_score": round(text[(x, y)], 3),
             "structural_agreement": round(agreement(x, y, current), 3), "score": round(s, 3)}
            for x, (y, s) in sorted(matched.items(), key=lambda kv: -kv[1][1])
        ],
        "rejected_for_cycles": [{"ctx_a": x, "ctx_b": y} for x, y in rejected],
    }


def contradictions(matrices: Iterable[Matrix], same_as: Iterable[tuple[Node, Node]]) -> list[set[Node]]:
    """Unit groups caught in a cycle once `same_as` pairs are merged."""
    merged = Merged(matrices)
    for x, y in same_as:
        if x in merged._rep and y in merged._rep:
            merged.merge(x, y)
    return merged.cycles()
