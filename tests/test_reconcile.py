"""Cross-document reconciliation tools on small hand-built matrices."""

import asyncio
import json

from fastmcp import Client

from harris_mcp.server import mcp


def hmdp(path, contexts, relations):
    path.write_text(json.dumps({
        "contexts": [{"id": i, "description": d, "period": p, "type": "deposit"} for i, d, p in contexts],
        "relations": [{"a": a, "b": b, "kind": "above"} for a, b in relations],
    }))
    return str(path)


def session(steps):
    async def go():
        async with Client(mcp) as c:
            async def call(name, **args):
                res = await c.call_tool(name, args)
                return res.structured_content if res.data is None or isinstance(res.data, dict) else res.data
            return await steps(call)
    return asyncio.run(go())


def test_structure_and_cycle_check(tmp_path):
    # A: x above y. B: p above q. Text favours the crossed pairing x~q, y~p,
    # which would make the merged sequence contradict itself.
    a = hmdp(tmp_path / "a.json", [("x", "dark brown silty clay charcoal", "P"),
                                   ("y", "grey sand shell", "P")], [("x", "y")])
    b = hmdp(tmp_path / "b.json", [("p", "grey sand shell pebbles", "P"),
                                   ("q", "dark brown silty clay charcoal", "P")], [("p", "q")])

    async def steps(call):
        ida = (await call("open_matrix", path=a))["matrix_id"]
        idb = (await call("open_matrix", path=b))["matrix_id"]
        plain = await call("propose_reconciliation", matrix_a=ida, matrix_b=idb,
                           structure_weight=0.0, check_cycles=False)
        checked = await call("propose_reconciliation", matrix_a=ida, matrix_b=idb)
        first = await call("assert_correspondence", matrix_a=ida, ctx_a="x", matrix_b=idb, ctx_b="q")
        second = await call("assert_correspondence", matrix_a=ida, ctx_a="y", matrix_b=idb, ctx_b="p")
        report = await call("check_correspondences", matrix_ids=[ida, idb])
        return plain, checked, first, second, report

    plain, checked, first, second, report = session(steps)
    pairs = lambda r: {(m["ctx_a"], m["ctx_b"]) for m in r["matches"]}
    assert pairs(plain) == {("x", "q"), ("y", "p")}
    assert pairs(checked) == {("x", "q")}
    assert checked["rejected_for_cycles"] == [{"ctx_a": "y", "ctx_b": "p"}]
    assert first["contradictions"] == []
    assert len(second["contradictions"]) == 1
    assert not report["consistent"]
    units = {(u["ctx"]) for u in report["contradictions"][0]["units"]}
    assert units == {"x", "y", "p", "q"}
    assert set(report["contradictions"][0]["correspondences"]) == {first["id"], second["id"]}


def test_structure_breaks_text_ties(tmp_path):
    # Two identical-looking units in B; only stratigraphy says which one is
    # the unit sitting under the (clearly matched) top layer.
    a = hmdp(tmp_path / "a.json", [("top", "white plaster floor", "P"), ("mid", "brown silt", "P"),
                                   ("low", "black ash", "P")], [("top", "mid"), ("mid", "low")])
    b = hmdp(tmp_path / "b.json", [("T", "white plaster floor", "P"), ("M1", "brown silt", "P"),
                                   ("M2", "brown silt", "P"), ("L", "black ash", "P")],
             [("M2", "T"), ("T", "M1"), ("M1", "L")])

    async def steps(call):
        ida = (await call("open_matrix", path=a))["matrix_id"]
        idb = (await call("open_matrix", path=b))["matrix_id"]
        return await call("propose_reconciliation", matrix_a=ida, matrix_b=idb)

    res = session(steps)
    match = {m["ctx_a"]: m for m in res["matches"]}
    assert match["mid"]["ctx_b"] == "M1"
    assert match["mid"]["structural_agreement"] == 1.0


def test_cross_reference_limit_and_filters(tmp_path):
    a = hmdp(tmp_path / "a.json", [("a1", "brown silt charcoal", "I")], [])
    b = hmdp(tmp_path / "b.json", [(f"b{i}", "brown silt" + " x" * i, "I") for i in range(5)]
             + [("exact", "brown silt charcoal", "II")], [])

    async def steps(call):
        ida = (await call("open_matrix", path=a))["matrix_id"]
        idb = (await call("open_matrix", path=b))["matrix_id"]
        top = await call("cross_reference", matrix_a=ida, matrix_b=idb, threshold=0.1, limit=1)
        same = await call("cross_reference", matrix_a=ida, matrix_b=idb, threshold=0.1, limit=1,
                          same_period=True)
        return top, same

    top, same = session(steps)
    assert [r["ctx_b"] for r in top] == ["exact"]  # best, not first found
    assert [r["ctx_b"] for r in same] == ["b0"]  # "exact" is in another period
