"""Regenerate the generated parts of docs/index.html.

    python -m docs.gen_reference

* the tool reference, from the server's own tool list and descriptions;
* the reconciliation results table, from sim/results/summary.csv;
* docs/assets/fig-reconcile-f1.svg, copied from sim/results/.

Fails if a tool exposed by the server is missing from GROUPS, so the page
cannot silently fall behind the server.
"""

from __future__ import annotations

import asyncio
import csv
import html
import re
import shutil
from pathlib import Path

from fastmcp import Client

from harris_mcp.server import mcp

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "index.html"
RESULTS = ROOT / "sim" / "results"

GROUPS = {
    "Load and save": ["open_matrix", "upload_matrix", "open_corpus", "close_matrix", "list_open_matrices", "save_matrix"],
    "Read units": ["get_context", "list_contexts", "count_contexts", "search_contexts"],
    "Read relations": ["neighbors", "ancestors", "descendants", "relation", "path", "between", "contemporaries"],
    "Whole matrix": ["topological_layers", "phases", "phase_sequence", "periods", "phase_contexts", "validate",
                     "summary", "anomalies", "describe_context", "describe_phase", "boundary_contexts"],
    "Edit (changelogged)": ["add_context", "update_context", "delete_context", "add_relation", "remove_relation",
                            "assign_phase", "mark_contemporary", "attach_note"],
    "Provenance": ["history", "revert", "diff"],
    "Cross-document": ["query_corpus", "cross_reference", "propose_reconciliation", "assert_correspondence",
                       "check_correspondences", "correspondences", "compare_phases", "compare_periods"],
    "Output": ["render", "subgraph", "export_geojson", "link_ohm_feature"],
}


def _first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    m = re.match(r"(.+?\.)(\s|$)", text)
    return m.group(1) if m else text


async def _tools() -> tuple[dict[str, str], list[str]]:
    async with Client(mcp) as c:
        tools = {t.name: _first_sentence(t.description) for t in await c.list_tools()}
        uris = [str(r.uri) for r in await c.list_resources()]
        uris += [r.uriTemplate for r in await c.list_resource_templates()]
    return tools, uris


def _inline_code(text: str) -> str:
    """Escape a description and render its `backticked` spans as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))


def tools_html(tools: dict[str, str], uris: list[str]) -> str:
    grouped = {n for names in GROUPS.values() for n in names}
    missing = sorted(set(tools) - grouped)
    stale = sorted(grouped - set(tools))
    if missing or stale:
        raise SystemExit(f"GROUPS out of date: missing {missing}, no longer served {stale}")
    out = ['<div class="hm-toolref">']
    for group, names in GROUPS.items():
        out.append(f'<section><h3>{html.escape(group)} <span>{len(names)}</span></h3><dl>')
        out += [f"<div><dt>{n}</dt><dd>{_inline_code(tools[n])}</dd></div>" for n in names]
        out.append("</dl></section>")
    out.append(f'<section><h3>Resources <span>{len(uris)}</span></h3><ul class="hm-resources">')
    out += [f"<li>{html.escape(u)}</li>" for u in sorted(uris)]
    out.append("</ul></section></div>")
    return "\n".join(out)


def results_html() -> str:
    rows = list(csv.DictReader((RESULTS / "summary.csv").open()))
    methods = list(dict.fromkeys(r["method"] for r in rows))
    scenarios = list(dict.fromkeys((r["overlap"], r["noise"], r["dropout"]) for r in rows))
    get = {(r["overlap"], r["noise"], r["dropout"], r["method"]): r for r in rows}

    def f(x):
        return f"{float(x):.2f}"

    trench = get[("trench", "0.2", "0.1", "+ structure")], get[("trench", "0.2", "0.1", "+ period/type")]
    full = get[("full", "0.2", "0.1", "+ structure")], get[("full", "0.2", "0.1", "+ period/type")]
    text_worst = max(float(r["contradicting_units_mean"]) for r in rows if r["method"] == "text")
    checked_worst = max(float(r["contradicting_units_mean"]) for r in rows
                        if r["method"] in ("+ cycle check", "+ structure"))
    n = rows[0]["n"]
    out = ['<div class="hm-figures">',
           f'<div><strong>{f(trench[0]["f1_mean"])} vs {f(trench[1]["f1_mean"])}</strong>'
           '<span>F1, structure vs period/type filter · trench · 20% noise</span></div>',
           f'<div><strong>{f(full[0]["f1_mean"])} vs {f(full[1]["f1_mean"])}</strong>'
           '<span>The same · full re-recording of 705 units</span></div>',
           f'<div><strong>{checked_worst:,.0f} vs {text_worst:,.0f}</strong>'
           '<span>Units in a contradiction · cycle check vs text alone</span></div>',
           "</div>",
           '<figure class="plate hm-plate" role="img" aria-label="Two line charts of F1 against description '
           'noise (0, 20%, 40%) for four reconcilers. In both the trench and the full re-recording scenario, '
           'adding structure scores highest at every noise level and text-only matching lowest.">'
           '<a href="assets/fig-reconcile-f1.svg" title="Open the figure at full size">'
           '<img src="assets/fig-reconcile-f1.svg" width="660" height="290" alt="" loading="lazy" decoding="async"></a>'
           '<span class="tick-bl" aria-hidden="true"></span><span class="tick-br" aria-hidden="true"></span></figure>',
           '<div class="plate-block__caption hm-caption"><span><strong>Fig. 1</strong> F1 of recovered same-as pairs</span>'
           f'<span><strong>Mean ± sd</strong> {n} seeds</span><span><strong>Dropout</strong> 10%</span></div>',
           '<div class="hm-table-scroll"><table class="hm-table"><thead><tr><th>Overlap</th><th>Noise</th><th>Dropout</th>']
    out += [f"<th>{html.escape(m)}</th>" for m in methods]
    out.append("</tr></thead><tbody>")
    for o, nz, d in scenarios:
        cells = [get[(o, nz, d, m)] for m in methods]
        best = max(float(c["f1_mean"]) for c in cells)
        out.append(f"<tr><td>{o}</td><td>{float(nz):.0%}</td><td>{float(d):.0%}</td>")
        for c in cells:
            v = f'{f(c["f1_mean"])} ± {f(c["f1_sd"])}'
            v = f"<strong>{v}</strong>" if float(c["f1_mean"]) == best else v
            out.append(f'<td class="num">{v}<small>{float(c["contradicting_units_mean"]):,.0f} in cycles</small></td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    out.append('<p class="marginalia">F1, mean ± sd over seeds; below it, units caught in a stratigraphic '
               'contradiction after merging. Best F1 per row in bold.</p>')
    return "\n".join(out)


def splice(page: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:start -->\n).*?(<!-- {name}:end -->)", re.S)
    if not pattern.search(page):
        raise SystemExit(f"marker {name} not found in {PAGE}")
    return pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), page)


def main() -> None:
    tools, uris = asyncio.run(_tools())
    page = PAGE.read_text(encoding="utf-8")
    page = splice(page, "tools", tools_html(tools, uris))
    page = splice(page, "results", results_html())
    PAGE.write_text(page, encoding="utf-8")
    (ROOT / "docs" / "assets").mkdir(exist_ok=True)
    shutil.copy(RESULTS / "fig-reconcile-f1.svg", ROOT / "docs" / "assets" / "fig-reconcile-f1.svg")
    print(f"updated {PAGE.relative_to(ROOT)}: {len(tools)} tools, {len(uris)} resources, results table")


if __name__ == "__main__":
    main()
