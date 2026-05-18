"""Rendering of a Harris matrix as Graphviz DOT / SVG / PNG.

Layers are placed using topological generations (the Hasse layout that is
the visual signature of a Harris matrix).
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Iterable

import networkx as nx

from .model import Matrix


def to_dot(matrix: Matrix, highlight: Iterable[str] = ()) -> str:
    g = matrix.graph
    hi = set(highlight)
    lines = ["digraph harris {", "  rankdir=TB;", "  node [shape=box, fontname=Helvetica];"]

    # Layered placement via topological generations (only valid on DAGs)
    try:
        generations = list(nx.topological_generations(g))
    except nx.NetworkXUnfeasible:
        generations = []

    for layer in generations:
        lines.append("  { rank=same; " + " ".join(f'"{n}"' for n in layer) + " }")

    for node in g.nodes:
        ctx = matrix.contexts.get(node)
        label = node
        if ctx and ctx.phase:
            label = f"{node}\\nphase {ctx.phase}"
        attrs = [f'label="{label}"']
        if node in hi:
            attrs.append('style=filled')
            attrs.append('fillcolor="#ffe066"')
        lines.append(f'  "{node}" [{", ".join(attrs)}];')

    for a, b in g.edges:
        lines.append(f'  "{a}" -> "{b}";')

    lines.append("}")
    return "\n".join(lines)


def render(matrix: Matrix, fmt: str = "svg", highlight: Iterable[str] = ()) -> bytes:
    dot = to_dot(matrix, highlight=highlight)
    if fmt == "dot":
        return dot.encode("utf-8")
    if not shutil.which("dot"):
        raise RuntimeError("graphviz `dot` binary not found on PATH; install graphviz")
    proc = subprocess.run(
        ["dot", f"-T{fmt}"],
        input=dot.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return proc.stdout
