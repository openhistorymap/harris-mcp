# harris-mcp

> **A Model Context Protocol server that makes Harris matrices first-class
> citizens of an LLM's working context — for archaeologists, by archaeologists
> (and the engineers who work with them).**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Built with FastMCP](https://img.shields.io/badge/built%20with-FastMCP-7c3aed.svg)](https://github.com/jlowin/fastmcp)
[![Project: Open History Map](https://img.shields.io/badge/project-Open%20History%20Map-1f6feb.svg)](https://www.openhistorymap.org/)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#status)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

`harris-mcp` exposes a Harris matrix — the partial-order graph
archaeologists use to record stratigraphy — as a typed, queryable,
auditably-editable resource over the [Model Context Protocol][mcp]. It is
designed for a workflow where the **deterministic graph work happens on
the server** and the **interpretive work happens on the LLM**, with every
LLM-driven edit landing on a per-matrix changelog that a human can read,
audit, and revert.

[mcp]: https://modelcontextprotocol.io/

## Why does this exist?

Harris matrices have been the canonical representation of archaeological
stratigraphy since the late 1970s, but the surrounding tooling is
GUI-bound, single-document, and fragmented across closed file formats.
The interesting interpretive work — reconciling matrices across trenches,
proposing phasings, narrating sequences — happens *outside* the file.

`harris-mcp` is a small open substrate that lets an LLM (or any MCP
client) do that interpretive work *with structured access to the matrix
itself*, instead of being shown a screenshot. The companion paper outline
in [`docs/paper-outline.md`](docs/paper-outline.md) goes into the
rationale at length.

## Features

- **Five file formats.** HMDP (an open JSON pivot format defined here),
  CSV (paired tables or single edge-list), XLSX. HMC and HMCX are
  best-effort read-only with a clear `NotImplementedError` fallback when
  the proprietary variant is unrecognised.
- **High-density reads tuned for LLM consumption.** `describe_context`
  returns a unit plus its 2-hop neighborhood plus phase membership plus
  any cross-document correspondences in one call — so the model doesn't
  have to chain ten tool calls to build the picture.
- **Audit-first writes.** Every mutation lands on a per-matrix changelog
  with `note` and `author`. `history`, `diff`, and `revert` are tools, not
  hidden machinery — the LLM's interpretive trail is a first-class
  artifact.
- **Cross-document corpus tools.** Load many matrices at once;
  `cross_reference` suggests candidate matches across trenches;
  `assert_correspondence` records the LLM's conclusions outside the
  source matrices, so round-trips to HMC/CSV don't erode them.
- **Open History Map integration.** Optional hooks for
  `export_geojson` and `link_ohm_feature` so stratigraphic data hands off
  cleanly to the rest of the [OHM ecosystem][ohm].
- **Apache 2.0 licensed.** Use it, fork it, ship it commercially —
  attribution and patent-grant rules per the licence.

[ohm]: https://www.openhistorymap.org/

## Quick start

### From source

```bash
git clone https://github.com/openhistorymap/harris-mcp.git
cd harris-mcp
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- MCP endpoint: `http://localhost:8000/mcp` (SSE transport)
- Health: `GET http://localhost:8000/` → JSON status

### With Docker

```bash
docker build -t harris-mcp .
docker run --rm -p 8000:8000 harris-mcp
```

### Wire it into an MCP client

Any MCP-compatible client (Claude Desktop, Claude Code, custom agents
built with FastMCP) can connect to the SSE endpoint above. See
`docs/paper-outline.md` §5 for worked example sessions.

## Tool surface at a glance

| Group | Tools |
|---|---|
| Load / save | `open_matrix`, `open_corpus`, `close_matrix`, `list_open_matrices`, `save_matrix` |
| Read units | `get_context`, `list_contexts`, `count_contexts`, `search_contexts` |
| Read relations | `neighbors`, `ancestors`, `descendants`, `relation`, `path`, `between`, `contemporaries` |
| Whole-matrix | `topological_layers`, `phases`, `periods`, `phase_contexts`, `validate`, `summary`, `anomalies`, `describe_context`, `describe_phase`, `boundary_contexts` |
| Edit (changelogged) | `add_context`, `update_context`, `delete_context`, `add_relation`, `remove_relation`, `assign_phase`, `mark_contemporary`, `attach_note` |
| Provenance | `history`, `revert`, `diff` |
| Cross-document | `query_corpus`, `cross_reference`, `assert_correspondence`, `correspondences`, `compare_phases`, `compare_periods` |
| Output | `render`, `subgraph`, `export_geojson`, `link_ohm_feature` |

Resources mirror the most useful reads as URIs:

```
harris://matrices
harris://matrix/{id}/summary
harris://matrix/{id}/context/{ctx}
harris://matrix/{id}/context/{ctx}/describe
harris://matrix/{id}/layers
harris://matrix/{id}/diagnostics
harris://corpus/correspondences
```

## Format support matrix

| Format | Read | Write | Notes |
|---|:---:|:---:|---|
| **HMDP** (`.hmdp.json` / `.json`) | ✅ | ✅ | Canonical open pivot; lossless |
| **CSV** (`contexts.csv` + `relations.csv`, or edge-list) | ✅ | ✅ | Two conventions accepted on read |
| **XLSX** | ✅ | ✅ | Sheets `contexts`, `relations` |
| **HMC** | ⚠️ best-effort | ❌ | Proprietary; export to CSV/XLSX from HMC |
| **HMCX** | ⚠️ best-effort | ❌ | Zipped XML; same caveat as HMC |

Help adding fuller HMC/HMCX support is very welcome — see
[Contributing](#contributing).

## Repository layout

```
app.py                    Starlette + SSE wiring (mirrors sibling OHM mcp/ services)
harris_mcp/
  model.py                Context, Relation, Matrix, ChangelogEntry, Correspondence
  registry.py             In-memory open-matrix registry + cross-doc table
  server.py               FastMCP tools + resources (the public surface)
  validate.py             Cycle / dangling / redundant-edge diagnostics
  render.py               Graphviz DOT/SVG/PNG renderer
  formats/
    hmdp.py  csv.py  xlsx.py  hmc.py  hmcx.py
docs/
  paper-outline.md        Companion paper outline (design rationale)
Dockerfile                Python 3.11 + graphviz
requirements.txt
LICENSE                   Apache License, Version 2.0
NOTICE
```

## Contributing

Contributions are very welcome — this is an explicitly open, community
project. By contributing you agree to license your contribution under the
Apache License 2.0 (see [LICENSE](LICENSE)).

**Good first issues**

- Better HMC/HMCX parsers (you have sample files? open an issue with one).
- Additional format adapters (GraphML, ArchEd, Stratify).
- A real test suite (`pytest`, fixtures under `tests/fixtures/`).
- Phase-order metadata (today phase ordering is lexical; let users supply
  an explicit phase sequence).
- Better Graphviz styling (per-type node shapes, equivalence-class boxes).

**Workflow**

1. Open an issue first for anything non-trivial — we'd rather discuss the
   shape of a change than rebase it.
2. Fork → feature branch → PR against `main`. Keep PRs focused.
3. Run the smoke test (see below) before opening the PR.
4. Commit messages: imperative mood, short subject, longer body if the
   *why* is non-obvious.

**Smoke test**

```bash
docker build -t harris-mcp:dev .
docker run --rm harris-mcp:dev python -c "
from harris_mcp.model import Context, Relation, Matrix
from harris_mcp.validate import validate
m = Matrix(id='t', name='t')
m.add_context(Context(id='1')); m.add_context(Context(id='2'))
m.add_relation(Relation(a='1', b='2', kind='above'))
assert validate(m)['valid']
print('ok')
"
```

**Reporting bugs**

Please include: format you were loading, a (redacted/anonymised if
necessary) excerpt of the file, the exact tool call, and the error or
unexpected output.

**Code of conduct**

Be kind. Assume good faith. Archaeology is a small world; everyone here
is trying to do good work. We follow the spirit of the
[Contributor Covenant][cc] — substantive disagreements are welcome,
personal attacks are not.

[cc]: https://www.contributor-covenant.org/

## Roadmap

- [ ] Reverse-engineered (or partner-supplied) HMC/HMCX read/write
- [ ] Explicit phase-ordering metadata
- [ ] Spatial coreference: suggest correspondences from context geometries
- [ ] Persistent storage backend (Mongo, matching the rest of OHM)
- [ ] Bibliographic linkage to [`ohmi`][ohmi] (Zotero-backed)
- [ ] Real test suite + CI
- [ ] Worked example archive under `examples/`

[ohmi]: https://github.com/openhistorymap

Have a use case we haven't thought of? [Open an issue][issues].

[issues]: https://github.com/openhistorymap/harris-mcp/issues

## Citation

If this software supports academic work, please cite both the software
and (when published) the companion paper. A `CITATION.cff` will be added
alongside the v1.0 release.

## Status

Alpha. The API surface is expected to evolve; expect minor breakage
between 0.x releases. The graph model and HMDP schema are intended to
remain stable.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).

See [`NOTICE`](NOTICE) for required attribution.

Copyright © 2026 Open History Map contributors.
