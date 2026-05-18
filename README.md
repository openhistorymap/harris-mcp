# harris-mcp

Model Context Protocol (MCP) server for reading, querying and (auditably)
editing Harris matrices — the partial-order graphs archaeologists use to
record stratigraphy. Built for large language models as the primary
client: deterministic structure on the server side, interpretation on the
LLM side, with every LLM edit landing on a per-matrix changelog.

Supported formats: HMDP (canonical JSON pivot), CSV, XLSX. HMC / HMCX
are read-only best-effort; round-trip via HMDP/CSV/XLSX is recommended.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

The MCP endpoint is exposed at `http://localhost:8000/mcp` (SSE).
`GET /` returns a health JSON payload.

## Docker

```bash
docker build -t harris-mcp .
docker run --rm -p 8000:8000 harris-mcp
```

## Layout

```
app.py                    Starlette + SSE wiring
harris_mcp/
  model.py                Context, Relation, Matrix, ChangelogEntry, ...
  registry.py             In-memory open-matrix registry + cross-doc table
  server.py               FastMCP tools + resources
  validate.py             Cycle / dangling / redundant-edge diagnostics
  render.py               Graphviz DOT/SVG/PNG renderer
  formats/
    hmdp.py  csv.py  xlsx.py  hmc.py  hmcx.py
docs/
  paper-outline.md        Companion paper outline
```

## Tool surface (overview)

- **Load / save**: `open_matrix`, `open_corpus`, `close_matrix`,
  `list_open_matrices`, `save_matrix`.
- **Read units**: `get_context`, `list_contexts`, `count_contexts`,
  `search_contexts`.
- **Read relationships**: `neighbors`, `ancestors`, `descendants`,
  `relation`, `path`, `between`, `contemporaries`.
- **Whole-matrix views**: `topological_layers`, `phases`, `periods`,
  `phase_contexts`, `validate`, `summary`, `anomalies`,
  `describe_context`, `describe_phase`, `boundary_contexts`.
- **Edit (changelogged)**: `add_context`, `update_context`,
  `delete_context`, `add_relation`, `remove_relation`, `assign_phase`,
  `mark_contemporary`, `attach_note`.
- **Provenance**: `history`, `revert`, `diff`.
- **Cross-document**: `query_corpus`, `cross_reference`,
  `assert_correspondence`, `correspondences`, `compare_phases`,
  `compare_periods`.
- **Output**: `render`, `subgraph`, `export_geojson`, `link_ohm_feature`.

Resources mirror the read tools under URIs like
`harris://matrix/{id}/summary`,
`harris://matrix/{id}/context/{ctx}/describe`,
`harris://corpus/correspondences`.

## Status

Early-stage; no test suite yet. See `docs/paper-outline.md` for the design
rationale and intended workflow.
