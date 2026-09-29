"""upload_matrix: matrices sent by content rather than server path."""

import asyncio
import base64
from pathlib import Path

import pytest
from fastmcp import Client

from harris_mcp import uploads
from harris_mcp.server import mcp

FIXTURES = Path(__file__).parent / "fixtures"
FIG12 = FIXTURES / "fig12"
HMCX = FIXTURES / "ulm-eggingen" / "Ulm-Eggingen_Strat.hmcx"


@pytest.fixture(autouse=True)
def upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "ROOT", tmp_path / "uploads")
    return tmp_path / "uploads"


def call(tool, **args):
    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args, raise_on_error=False)
    return asyncio.run(go())


def test_upload_hm_package_as_text():
    files = {p.name: p.read_text(encoding="utf-8") for p in FIG12.iterdir()}
    res = call("upload_matrix", files=files, name="Harris fig. 12")
    out = res.structured_content
    assert not res.is_error
    assert out["name"] == "Harris fig. 12"
    assert out["matrix_id"].startswith("Harris-fig-12-")
    assert (out["n_contexts"], out["n_edges"]) == (19, 27)
    assert out["diagnostics"]["valid"]
    assert out["phase_sequence"] == {"sequence": [["Phase II"], ["Phase I"]], "conflicts": []}
    assert out["anomalies"] == {"count": 0, "first": []}
    # The handle works with every other tool.
    layers = call("topological_layers", matrix_id=out["matrix_id"]).data
    assert layers[0] == ["Natural ground"]


def test_upload_hmcx_as_base64():
    blob = base64.b64encode(HMCX.read_bytes()).decode("ascii")
    out = call("upload_matrix", files={HMCX.name: blob}, encoding="base64").structured_content
    assert out["matrix_id"].startswith("Ulm-Eggingen_Strat-")
    assert (out["n_contexts"], out["n_edges"]) == (110, 192)


def test_upload_single_edge_list():
    out = call("upload_matrix", files={"edges.csv": "above,below\nA,B\nB,C\n"}).structured_content
    assert (out["n_contexts"], out["n_edges"], out["depth"]) == (3, 2, 3)


@pytest.mark.parametrize("files, encoding, message", [
    ({"../evil.csv": "above,below\nA,B\n"}, "text", "plain file name"),
    ({"sub/dir.csv": "above,below\nA,B\n"}, "text", "plain file name"),
    ({"site.hmcx": "not really"}, "text", "base64"),
    ({"edges.csv": "!!!not base64!!!"}, "base64", "not valid base64"),
    ({}, "text", "no files"),
])
def test_rejected_uploads(files, encoding, message, upload_root):
    with pytest.raises(uploads.UploadError, match=message):
        uploads.load(files, encoding=encoding)
    assert not upload_root.exists() or not any(upload_root.iterdir())


def test_limits(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_BYTES", 10)
    with pytest.raises(uploads.UploadError, match="too large"):
        uploads.load({"edges.csv": "above,below\nA,B\n"})
    monkeypatch.setattr(uploads, "MAX_FILES", 1)
    with pytest.raises(uploads.UploadError, match="too many files"):
        uploads.load({"a.csv": "x", "b.csv": "y"})


def test_failed_load_leaves_nothing(upload_root):
    res = call("upload_matrix", files={"notes.csv": "hello,world\n1,2\n"})
    assert res.is_error
    assert "does not look like" in res.content[0].text
    assert not any(upload_root.iterdir())


def test_only_recent_uploads_kept(monkeypatch, upload_root):
    monkeypatch.setattr(uploads, "KEEP", 2)
    for i in range(3):
        uploads.load({f"e{i}.csv": "above,below\nA,B\n"})
    kept = sorted(p.name for p in upload_root.iterdir())
    assert len(kept) == 2
