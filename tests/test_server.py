"""Server tools over an in-memory MCP client, on the fig12 data package."""

import asyncio
import base64
from pathlib import Path

import pytest
from fastmcp import Client

from harris_mcp.server import mcp

FIG12 = Path(__file__).parent / "fixtures" / "fig12"


def run(*calls):
    """Open fig12, then run `calls` (name, args) in order; return their data."""

    async def go():
        async with Client(mcp) as c:
            opened = (await c.call_tool("open_matrix", {"path": str(FIG12)})).data
            out = [opened]
            for name, args in calls:
                res = await c.call_tool(name, {"matrix_id": opened["matrix_id"], **args})
                out.append(res.structured_content if res.data is None else res.data)
            return out

    return asyncio.run(go())


def test_open_matrix_diagnostics():
    (opened,) = run()
    assert opened["n_contexts"] == 19
    assert opened["n_edges"] == 27
    d = opened["diagnostics"]
    assert d["valid"] and not d["cycles"] and not d["dangling"]


def test_topological_layers_earliest_first():
    _, layers = run(("topological_layers", {}))
    assert layers[0] == ["Natural ground"]
    assert layers[-1] == ["10"]


def test_phase_sequence_is_inferred_from_stratigraphy():
    _, seq = run(("phase_sequence", {}))
    assert seq == {"sequence": [["Phase II"], ["Phase I"]], "conflicts": []}


def test_no_anomalies_without_phase_order():
    _, found = run(("anomalies", {}))
    assert found == []


def test_anomalies_with_explicit_phase_order():
    _, right, wrong = run(
        ("anomalies", {"phase_order": ["Phase II", "Phase I"]}),
        ("anomalies", {"phase_order": ["Phase I", "Phase II"]}),
    )
    assert right == []
    # Wrong order: every edge that crosses the phase boundary is flagged.
    assert sorted((a["a"], a["b"]) for a in wrong) == [("6", "9"), ("7", "15"), ("8", "16")]


def test_describe_phase_boundaries():
    _, phase = run(("describe_phase", {"phase": "Phase II"}))
    assert phase["boundary_above"] == ["6", "7", "8"]
    assert phase["anomalies"] == []


def test_relations_and_contemporaries():
    _, above, below, contemporaries = run(
        ("relation", {"a": "10", "b": "Natural ground"}),
        ("relation", {"a": "3", "b": "4"}),
        ("contemporaries", {"ctx": "7"}),
    )
    assert above == "above"
    assert below == "below"
    assert contemporaries == ["8"]


@pytest.mark.skipif(not __import__("shutil").which("dot"), reason="graphviz not installed")
def test_render_svg():
    _, rendered = run(("render", {"fmt": "svg"}))
    assert b"<svg" in base64.b64decode(rendered["base64"])


def test_hmcx_through_mcp():
    path = Path(__file__).parent / "fixtures" / "ulm-eggingen" / "Ulm-Eggingen_Strat.hmcx"

    async def go():
        async with Client(mcp) as c:
            opened = (await c.call_tool("open_matrix", {"path": str(path)})).data
            layers = (await c.call_tool("topological_layers", {"matrix_id": opened["matrix_id"]})).data
            return opened, layers

    opened, layers = asyncio.run(go())
    assert opened["diagnostics"]["valid"]
    assert layers[0] == ["G"] and layers[-1] == ["T"]


def test_neighbors_and_ancestry_directions():
    # fig12: 7 lies above 15, 15 above 9 (observations younger -> older).
    _, nb, earlier, later, described = run(
        ("neighbors", {"ctx": "15"}),
        ("ancestors", {"ctx": "15"}),
        ("descendants", {"ctx": "15"}),
        ("describe_context", {"ctx": "15", "neighborhood": 1}),
    )
    assert nb == {"above": ["7"], "below": ["9"], "contemporary": ["16"]}
    assert earlier == ["18", "9", "Natural ground"]
    assert "10" in later and "9" not in later
    assert described["neighborhood"] == nb
    assert described["ancestors"] == earlier
