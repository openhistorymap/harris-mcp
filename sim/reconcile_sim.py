"""Simulated stratigraphic unit reconciliation.

Ground truth is a real matrix (default: Çatalhöyük East Mound, Buildings 1
and 5; see sim/README.md). Two teams record overlapping parts of it, each
with its own numbering, its own wording of every unit's description,
missed relations, and (team B) units split in two or merged with a
neighbour. Four reconcilers, an ablation of `propose_reconciliation`, then
try to recover which units are the same; each is scored against the truth.

All reconciliation goes through the MCP tools of `harris_mcp.server` over an
in-memory client, so the numbers describe what the server ships.

    python -m sim.reconcile_sim --data /data/catalhoyuk-bldg-1-5 --out sim/results
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from fastmcp import Client

import harris_mcp
from harris_mcp import formats, reconcile, registry
from harris_mcp.server import mcp

# --------------------------------------------------------------------------- #
# Hidden "true" descriptions                                                  #
# --------------------------------------------------------------------------- #

COLOURS = ["black", "very dark brown", "dark brown", "brown", "yellowish brown",
           "light brown", "greyish brown", "grey", "light grey", "white"]
TEXTURES = ["clay", "silty clay", "clayey silt", "silt", "sandy silt", "silty sand", "sand", "loam"]
COMPACTION = ["loose", "friable", "firm", "compact"]
INCLUSIONS = ["charcoal", "phytoliths", "bone", "plaster fragments", "burnt brick",
              "ash lenses", "shell", "obsidian", "pebbles"]
CUT_SHAPES = ["steep sides", "gradual sides", "flat base", "concave base", "irregular edge",
              "sub-circular plan", "linear plan"]


def true_description(rng: random.Random, unit_type: str) -> dict:
    if unit_type == "interface":
        return {"kind": "cut", "shape": rng.sample(CUT_SHAPES, 2)}
    return {
        "kind": "deposit",
        "colour": rng.randrange(len(COLOURS)),
        "texture": rng.randrange(len(TEXTURES)),
        "compaction": rng.randrange(len(COMPACTION)),
        "inclusions": rng.sample(INCLUSIONS, rng.randint(0, 3)),
    }


def observe(rng: random.Random, d: dict, noise: float) -> str:
    """One recorder's wording: each attribute drifts with probability `noise`
    (ordinal attributes to an adjacent value), inclusions may be missed or
    added."""
    def nudge(i: int, n: int) -> int:
        return min(n - 1, max(0, i + rng.choice([-1, 1]))) if rng.random() < noise else i

    if d["kind"] == "cut":
        shape = [s if rng.random() >= noise else rng.choice(CUT_SHAPES) for s in d["shape"]]
        return "cut with " + " and ".join(shape)
    inc = [i for i in d["inclusions"] if rng.random() >= noise]
    if rng.random() < noise:
        inc.append(rng.choice(INCLUSIONS))
    text = (f"{COMPACTION[nudge(d['compaction'], len(COMPACTION))]} "
            f"{COLOURS[nudge(d['colour'], len(COLOURS))]} "
            f"{TEXTURES[nudge(d['texture'], len(TEXTURES))]}")
    return text + (" with " + ", ".join(sorted(set(inc))) if inc else "")


# --------------------------------------------------------------------------- #
# One team's record                                                           #
# --------------------------------------------------------------------------- #


@dataclass
class Record:
    name: str
    contexts: dict[str, dict] = field(default_factory=dict)    # recorded id -> context
    edges: set[tuple[str, str]] = field(default_factory=set)   # (above, below)
    covers: dict[str, set[str]] = field(default_factory=dict)  # recorded id -> true units


def record(rng: random.Random, truth: nx.DiGraph, units: list[str], meta: dict, desc: dict,
           name: str, first_number: int, shared: set[str], *, noise: float, dropout: float,
           split: float, lump: float) -> Record:
    rec = Record(name)
    # Built explicitly, in the ground truth's order: a networkx subgraph view
    # iterates a node subset in hash order, which would make the random draws
    # below depend on PYTHONHASHSEED.
    keep = set(units)
    g = nx.DiGraph()
    g.add_nodes_from(units)
    g.add_edges_from((a, b) for a, b in truth.edges if a in keep and b in keep)
    owner = {u: u for u in units}

    # Lumping: two adjacent shared units recorded as one, only where the
    # direct relation is the sole path between them (else it is a cycle).
    for a, b in list(g.edges):
        if (a in shared and b in shared and owner[a] == a and owner[b] == b
                and g.has_edge(a, b) and rng.random() < lump):
            h = g.copy()
            h.remove_edge(a, b)
            if not nx.has_path(h, a, b):
                g = nx.contracted_nodes(g, a, b, self_loops=False)
                owner[b] = a
    reps = [u for u in units if owner[u] == u]

    # Numbering is shuffled so identifiers carry no information.
    numbers = rng.sample(range(first_number, first_number + 10 * len(units)), 2 * len(reps))
    rid: dict[str, list[str]] = {}
    for i, u in enumerate(reps):
        members = {x for x in units if owner[x] == u}
        if u in shared and rng.random() < split:
            top, bottom = str(numbers[2 * i]), str(numbers[2 * i + 1])
            rid[u] = [top, bottom]
            rec.edges.add((top, bottom))
        else:
            rid[u] = [str(numbers[2 * i])]
        for r in rid[u]:
            rec.covers[r] = members
            rec.contexts[r] = {"id": r, "type": meta[u]["type"], "period": meta[u]["period"],
                               "description": observe(rng, desc[u], noise)}
    for a, b in g.edges:
        if rng.random() >= dropout:
            rec.edges.add((rid[a][-1], rid[b][0]))
    return rec


def write_hmdp(rec: Record, path: Path) -> None:
    path.write_text(json.dumps({
        "name": rec.name,
        "contexts": list(rec.contexts.values()),
        "relations": [{"a": a, "b": b, "kind": "above"} for a, b in sorted(rec.edges)],
    }))


# --------------------------------------------------------------------------- #
# Experiment                                                                  #
# --------------------------------------------------------------------------- #

# Cumulative ablation of propose_reconciliation's options.
METHODS = {
    "text": dict(same_period=False, same_type=False, structure_weight=0.0, check_cycles=False),
    "+ period/type": dict(same_period=True, same_type=True, structure_weight=0.0, check_cycles=False),
    "+ cycle check": dict(same_period=True, same_type=True, structure_weight=0.0, check_cycles=True),
    "+ structure": dict(same_period=True, same_type=True, structure_weight=0.5, check_cycles=True),
}
THRESHOLD = 0.3
# "trench" overlap: the periods each team excavates; the shared ones are the overlap.
TRENCH = {"a": ["Building 1", "Outside"], "b": ["Building 5", "Outside"]}

SCENARIOS = [
    {"overlap": overlap, "noise": noise, "dropout": dropout, "split": 0.05, "lump": 0.05}
    for overlap in ("trench", "full")
    for noise, dropout in ((0.0, 0.1), (0.2, 0.1), (0.4, 0.1), (0.4, 0.3))
]


def truth_pairs(a: Record, b: Record) -> set[tuple[str, str]]:
    return {(x, y) for x, cx in a.covers.items() for y, cy in b.covers.items() if cx & cy}


async def run_once(c: Client, site, scenario: dict, seed: int, tmp: Path, exercise_asserts: bool) -> list[dict]:
    rng = random.Random(seed)
    truth = site.graph
    meta = {u: {"type": ctx.type, "period": ctx.period} for u, ctx in site.contexts.items()}
    desc = {u: true_description(rng, meta[u]["type"]) for u in truth.nodes}
    if scenario["overlap"] == "trench":
        units_a = [u for u in truth.nodes if meta[u]["period"] in TRENCH["a"]]
        units_b = [u for u in truth.nodes if meta[u]["period"] in TRENCH["b"]]
    else:
        units_a = units_b = list(truth.nodes)
    shared = set(units_a) & set(units_b)
    noise = {k: scenario[k] for k in ("noise", "dropout")}
    a = record(rng, truth, units_a, meta, desc, "team-A", 1000, shared, **noise, split=0.0, lump=0.0)
    b = record(rng, truth, units_b, meta, desc, "team-B", 50000, shared, **noise,
               split=scenario["split"], lump=scenario["lump"])
    write_hmdp(a, tmp / "a.json")
    write_hmdp(b, tmp / "b.json")
    ida = (await c.call_tool("open_matrix", {"path": str(tmp / "a.json")})).data["matrix_id"]
    idb = (await c.call_tool("open_matrix", {"path": str(tmp / "b.json")})).data["matrix_id"]
    ma, mb = registry.get(ida), registry.get(idb)
    truth_p = truth_pairs(a, b)

    rows = []
    for method, options in METHODS.items():
        res = (await c.call_tool("propose_reconciliation", {
            "matrix_a": ida, "matrix_b": idb, "threshold": THRESHOLD, **options})).structured_content
        found = {(m["ctx_a"], m["ctx_b"]) for m in res["matches"]}
        tp = len(found & truth_p)
        p = tp / len(found) if found else 1.0
        r = tp / len(truth_p) if truth_p else 1.0
        cyclic = reconcile.contradictions([ma, mb], [((ida, x), (idb, y)) for x, y in found])
        rows.append({
            **scenario, "seed": seed, "method": method,
            "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "contradicting_units": sum(len(g) for g in cyclic),
            "matches": len(found), "true_pairs": len(truth_p), "candidates": res["n_candidates"],
            "units_a": len(a.contexts), "units_b": len(b.contexts),
        })
        if exercise_asserts and method == "+ structure":
            # Record the proposal through the MCP surface and have the server
            # confirm it is free of contradictions.
            for x, y in found:
                await c.call_tool("assert_correspondence", {
                    "matrix_a": ida, "ctx_a": x, "matrix_b": idb, "ctx_b": y,
                    "note": "reconcile_sim", "author": "sim"})
            check = (await c.call_tool("check_correspondences", {"matrix_ids": [ida, idb]})).structured_content
            assert check["consistent"], check
    for mid in (ida, idb):
        await c.call_tool("close_matrix", {"matrix_id": mid})
    return rows


METRICS = ("precision", "recall", "f1", "contradicting_units")
KEYS = ("overlap", "noise", "dropout", "split", "lump", "method")


def summarise(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in KEYS), []).append(r)
    out = []
    for key, rs in groups.items():
        row = dict(zip(KEYS, key))
        row["n"] = len(rs)
        for k in METRICS + ("true_pairs", "candidates"):
            vals = [r[k] for r in rs]
            row[f"{k}_mean"] = statistics.mean(vals)
            row[f"{k}_sd"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        out.append(row)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def write_tables(out: Path, summary: list[dict]) -> None:
    methods = list(METHODS)
    scen = []
    for s in summary:
        k = (s["overlap"], s["noise"], s["dropout"])
        if k not in scen:
            scen.append(k)

    def cell(overlap, noise, dropout, method):
        s = next(x for x in summary if (x["overlap"], x["noise"], x["dropout"], x["method"])
                 == (overlap, noise, dropout, method))
        return s

    n = summary[0]["n"]
    md = ["| Overlap | Noise | Dropout | " + " | ".join(methods) + " |",
          "|---|---|---|" + "---|" * len(methods)]
    tex = [r"\begin{tabular}{llr" + "r" * len(methods) + "}", r"\toprule",
           "Overlap & Noise & Dropout & " + " & ".join(m.replace("+", r"\texttt{+}") for m in methods) + r" \\",
           r"\midrule"]
    for overlap, noise, dropout in scen:
        cells = [cell(overlap, noise, dropout, m) for m in methods]
        best = max(c["f1_mean"] for c in cells)
        md_cells, tex_cells = [], []
        for c in cells:
            f1 = f"{c['f1_mean']:.2f} ± {c['f1_sd']:.2f}"
            con = f"{c['contradicting_units_mean']:.0f}"
            md_cells.append((f"**{f1}**" if c["f1_mean"] == best else f1) + f" ({con})")
            tf = f"${c['f1_mean']:.2f} \\pm {c['f1_sd']:.2f}$"
            tex_cells.append((f"\\textbf{{{tf}}}" if c["f1_mean"] == best else tf) + f" ({con})")
        md.append(f"| {overlap} | {noise} | {dropout} | " + " | ".join(md_cells) + " |")
        tex.append(f"{overlap} & {noise} & {dropout} & " + " & ".join(tex_cells) + r" \\")
    tex += [r"\bottomrule", r"\end{tabular}"]
    caption = (f"F1 of recovered same-as pairs, mean ± sd over {n} seeds; in brackets the mean number "
               "of units caught in a stratigraphic contradiction after merging. Best F1 per row in bold.")
    (out / "summary.md").write_text(caption + "\n\n" + "\n".join(md) + "\n")
    (out / "summary.tex").write_text(f"% {caption}\n" + "\n".join(tex) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main(args) -> None:
    data = Path(args.data)
    site = formats.load(data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rows: list[dict] = []
    async with Client(mcp) as c:
        with tempfile.TemporaryDirectory() as tmp:
            for sc in SCENARIOS:
                for seed in range(args.seeds):
                    rows += await run_once(c, site, sc, seed, Path(tmp), exercise_asserts=seed == 0)
                print(f"{sc['overlap']:6} noise={sc['noise']} dropout={sc['dropout']}: "
                      + "  ".join(f"{m} F1 {statistics.mean(r['f1'] for r in rows if r['method'] == m and all(r[k] == sc[k] for k in sc)):.2f}"
                                  for m in METHODS), flush=True)
    summary = summarise(rows)
    write_csv(out / "runs.csv", rows)
    write_csv(out / "summary.csv", summary)
    write_tables(out, summary)
    files = sorted(p for p in data.rglob("*") if p.is_file()) if data.is_dir() else [data]
    (out / "meta.json").write_text(json.dumps({
        "data": {"path": str(data), "matrix": site.name, "contexts": len(site.contexts),
                 "relations": site.graph.number_of_edges(),
                 "sha256": {p.name: sha256(p) for p in files}},
        "seeds": list(range(args.seeds)),
        "threshold": THRESHOLD,
        "trench": TRENCH,
        "methods": METHODS,
        "scenarios": SCENARIOS,
        "harris_mcp": {"version": harris_mcp.__version__, "commit": os.environ.get("HARRIS_MCP_COMMIT", "unknown")},
        "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ("networkx", "fastmcp", "pydantic")},
        "runtime_seconds": round(time.time() - started, 1),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2))
    print(f"wrote {out}/runs.csv, summary.csv, summary.md, summary.tex, meta.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="/data/catalhoyuk-bldg-1-5", help="ground-truth matrix (any loadable path)")
    ap.add_argument("--out", default="sim/results", help="output directory")
    ap.add_argument("--seeds", type=int, default=10, help="replicates per scenario")
    ap.add_argument("--trench-a", default=",".join(TRENCH["a"]), help="periods recorded by team A (trench overlap)")
    ap.add_argument("--trench-b", default=",".join(TRENCH["b"]), help="periods recorded by team B (trench overlap)")
    args = ap.parse_args()
    TRENCH.update(a=args.trench_a.split(","), b=args.trench_b.split(","))
    asyncio.run(main(args))
