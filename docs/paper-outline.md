# Paper outline — *An MCP server for LLM-assisted reading and interpretation of Harris matrices*

> Working draft outline. Section numbering matches the order you would write
> in. Each bullet is a paragraph-sized claim with a hint at the evidence or
> example to use.

---

## Working titles (pick one)

1. *Reading the strata: a Model Context Protocol server for LLM-assisted interpretation of Harris matrices*
2. *From file to interpretation: an MCP backend for multi-document stratigraphic reasoning*
3. *Harris-MCP: exposing stratigraphic graphs to large language models for cross-trench interpretation*

## Target venues

- **Journal**: *Journal of Computer Applications in Archaeology* (JCAA), *Internet Archaeology*, *Archaeological Prospection* (methods section).
- **Conference**: CAA International (Computer Applications and Quantitative Methods in Archaeology), short paper or methods workshop.
- **Adjacent venues** if reframed toward tooling: *SoftwareX*, *Journal of Open Source Software* (short software paper).

## Abstract (≈ 200 words, draft last)

- Position: Harris matrices are the canonical representation of archaeological
  stratigraphy, but the tooling ecosystem is GUI-bound, single-document, and
  closed-format. The interpretive work — assigning phases, reconciling
  trenches, narrating sequences — happens outside the file.
- Proposal: a Model Context Protocol (MCP) server that exposes a Harris matrix
  as a typed, queryable, editable graph, with first-class support for
  multi-document corpora and an auditable changelog of LLM-generated
  interpretive assertions.
- Contribution: (i) a canonical pivot data model (HMDP) decoupled from vendor
  formats; (ii) a tool/resource surface tuned for LLM reasoning rather than
  GUI manipulation; (iii) a cross-document layer for trench-to-trench
  correspondence; (iv) an open-source reference implementation integrated with
  the Open History Map ecosystem.
- Evaluation hook: a worked example reconciling two trench matrices from
  [site to be named] and a discussion of how interpretive provenance changes
  the LLM's role from "answer generator" to "auditable collaborator".

## Keywords

Harris matrix · stratigraphy · Model Context Protocol · large language models
· archaeological interpretation · digital archaeology · graph databases ·
provenance

---

## 1. Introduction

- **1.1 The Harris matrix as representational artifact.** Brief history (Edward
  Harris, 1973–1979); its function as a *partial-order* abstraction of
  excavation; its dual role as recording instrument and interpretive medium.
- **1.2 The current tooling ecosystem.** Harris Matrix Composer (HMC/HMCX),
  ArchEd, Stratify, gvSIG, ad-hoc CSV/XLSX workflows. Common properties:
  GUI-bound, single-document, format-fragmented, weak on cross-trench
  reasoning. Cite the persistence of pen-and-paper diagrams in field reports
  even where digital tools are available.
- **1.3 The interpretive bottleneck.** The hard work is not drawing the graph;
  it is (a) assigning phases consistently, (b) reconciling matrices across
  trenches/sites, (c) integrating with bibliography and GIS, (d) narrating
  the sequence in publication. These are *reading* and *interpretation*
  tasks, not editing tasks.
- **1.4 Why LLMs, why now.** LLMs are competent at pattern matching across
  unstructured descriptions, at proposing equivalences, at narrating
  partial orders. They are weak at faithful structural manipulation and at
  honest uncertainty. The right division of labour is: deterministic tool
  for structure, LLM for interpretation, with provenance keeping the two
  separable.
- **1.5 Contribution.**
    - A canonical data model (HMDP) decoupled from proprietary formats.
    - An MCP server (`harris-mcp`) that exposes Harris matrices as queryable,
      editable graphs.
    - A *high-density read* surface tuned to how LLMs actually consume
      context (neighborhoods, not single nodes).
    - A *cross-document* layer for corpus-level reasoning.
    - A *provenance* layer (changelog + revert) that frames every LLM edit
      as an auditable interpretive claim.
    - An open-source reference implementation released under the
      Open History Map umbrella.
- **1.6 Paper structure.** One-paragraph map to the rest of the paper.

## 2. Background

- **2.1 The Harris matrix.** Formal definition: a Hasse diagram of a
  partial order over stratigraphic units, with auxiliary equivalence
  classes for *contemporary with* / *same as*. Notation conventions
  (above/below, cuts/cut-by, fills/filled-by, abuts). The role of phases
  and periods as a coarser quotient of the order.
- **2.2 File formats in the wild.**
    - **HMC / HMCX**: proprietary native formats of Harris Matrix Composer,
      effectively the de facto standard; closed but widely exchanged.
    - **CSV / XLSX**: ad-hoc, no agreed schema; in practice two conventions
      dominate — paired `contexts` + `relations` tables, or a flat
      `above,below` edge list.
    - **HMDP** (proposed here): a small JSON-based "Harris Matrix Data
      Package" inspired by Frictionless Data Packages, used as the
      canonical pivot.
    - Briefly: graph formats (GraphML, DOT) and why they under-specify the
      archaeological semantics.
- **2.3 The Model Context Protocol.** One paragraph: MCP as a standard for
  exposing tools and resources to LLM agents over a typed, streamable
  interface. Why this matters here: it lets the matrix become a *first-class
  citizen* of an LLM's working context, rather than a file the LLM is told
  about.
- **2.4 LLMs in archaeology, briefly.** Survey, in 2–3 paragraphs: current
  uses (text mining of grey literature, OCR of field notebooks, image
  classification, dating assistance). Limitations: hallucination,
  provenance erosion, fragility on structured data. Position our work as a
  *substrate* problem, not a model problem.

## 3. Design

- **3.1 Architecture overview.** One figure: client (LLM) ↔ MCP transport
  ↔ FastMCP server ↔ in-memory `Matrix` registry ↔ format adapters ↔
  files. Note the deliberate absence of a persistent database in the core
  scope, and the optional Mongo backing as future work.
- **3.2 HMDP as canonical pivot.** Argue the design choice: an N-format
  ecosystem requires either N² converters or one canonical model.
  Define HMDP minimally (schema in appendix). Every adapter parses *into*
  and serialises *out of* HMDP; render/validate/query operate on the pivot.
- **3.3 Read surface — high-density neighborhoods.** Argue that LLM
  consumption patterns differ from GUI consumption: a human scrolls a
  diagram, an LLM ingests a payload. Tools should return *interpretively
  useful chunks* — a context plus its 2-hop neighborhood plus its phase
  membership plus any cross-document correspondences — in a single call.
  Contrast with naive "one tool per attribute" surfaces.
- **3.4 Write surface — interpretation as auditable assertion.** Frame
  every mutation as an interpretive claim. Edits carry a `note` and
  `author`; they land on a per-matrix changelog; they can be reverted
  without losing later independent edits. This is *not* a transaction log,
  it is a *reasoning log* — designed for the human archaeologist who will
  read what the LLM did and decide whether to keep it.
- **3.5 Cross-document layer.** The corpus, not the file, is the unit of
  interpretation. Define correspondences as *typed cross-graph edges*
  (`same_as`, `contemporary_with`) stored outside the source matrices so
  that round-tripping to HMC/CSV does not erode them. Discuss the
  trade-off versus inlining correspondences into each matrix's `attrs`.
  Reconciliation support is deterministic and advisory:
  `propose_reconciliation` suggests a consistent 1:1 matching (description
  similarity + stratigraphic agreement + a refusal of matches that would
  create a cycle), nothing is written until the LLM or the human asserts;
  `check_correspondences` re-checks the whole asserted set, and
  `assert_correspondence` reports — but does not refuse — a contradiction
  it introduces. Evaluated in §5.4.
- **3.6 Provenance and changelog model.** Schema for changelog entries;
  what counts as one entry; how revert composes; the deliberate decision
  *not* to use Git-style branching (would conflate code-version semantics
  with interpretive-claim semantics).
- **3.7 What is out of scope (and why).** No spatial reasoning over
  context geometries; no automatic phase inference; no built-in
  bibliographic ingest. Each is a candidate for a downstream MCP server
  composed with this one.

## 4. Implementation

- **4.1 Stack.** Python 3.11, FastMCP, Starlette, `networkx`, Pydantic v2.
  Rationale for each choice in one sentence.
- **4.2 Module layout.** Mirror the directory tree from the repo; one
  paragraph per module on responsibility.
- **4.3 Format adapters in detail.** HMDP (canonical), CSV (two
  conventions), XLSX (openpyxl), T. S. Dye's hm tables (Frictionless data
  package or hm `.ini` project). HMC/HMCX: proprietary and undocumented,
  but HMC 2.x writes GraphML inside the `.hmcx` zip and exports a
  semicolon CSV; both are now read (verified against Rosenstock's
  Ulm-Eggingen files, where the two encodings load to the same matrix —
  except one phase group that the two published files place in different
  periods). No write support. Frame the situation as a *political* problem
  (closed standard in a discipline that values openness), not just a
  technical one.
- **4.4 Validation.** Cycle detection, dangling-reference detection,
  redundant-edge detection via transitive reduction. Note that validation
  runs eagerly at load time so the LLM never operates on a structurally
  invalid graph.
- **4.5 Rendering.** Graphviz `dot` with `rank=same` per topological
  generation; SVG/PNG/DOT outputs; highlight set for query results.
- **4.6 OHM integration hooks.** `link_ohm_feature`, `export_geojson`,
  optional Mongo persistence — wired to the Open History Map shared
  infrastructure but kept optional so the server is useful standalone.
- **4.7 Deployment.** Docker image, `uvicorn` entrypoint, mount under
  `/mcp` via SSE in line with the rest of the OHM `mcp/` family.

## 5. Worked examples

Three short scenarios, each ≤ 1 page. Each example should give: (a) the
question the archaeologist would ask, (b) the sequence of MCP calls the
LLM would make, (c) the output, (d) the human-auditable changelog.

- **5.1 Single-matrix interpretation.** Load one trench matrix; ask the
  LLM to propose a phasing from descriptions alone; commit the
  assignments with notes; show the diff.
- **5.2 Multi-trench correspondence.** Load two trench matrices from the
  same site; run `propose_reconciliation`; have the LLM triage the proposal
  (text score and structural agreement per pair, plus the pairs rejected
  for contradicting the sequence); record `same_as` correspondences;
  confirm with `check_correspondences`; render a merged diagram.
- **5.3 Hand-off to GIS.** Export contexts with geometry as GeoJSON for
  `ohm_importer`; round-trip through the OHM stack; comment on what the
  Harris layer adds to a purely spatial representation.

- **5.4 Simulated evaluation: unit reconciliation.** Not an LLM benchmark
  (see notes below) — a test of the substrate's deterministic support.
  Ground truth: Çatalhöyük Bldg 1–5 (705 units, 852 relations). Two
  simulated teams record overlapping parts with their own numbering, noisy
  descriptions, missed relations, split and lumped units; a cumulative
  ablation of `propose_reconciliation` is scored against the truth.
  Design, parameters and caveats: `sim/README.md`. Table:
  `sim/results/summary.tex`; figure: `sim/results/fig-reconcile-f1.pdf`;
  raw per-seed data: `sim/results/runs.csv`; provenance:
  `sim/results/meta.json`. Headline findings: RESULTS_PLACEHOLDER

## 6. Discussion

- **6.1 What the MCP/LLM split enables.** Move from *editor* to
  *interlocutor*. The archaeologist no longer "uses HMC"; they *talk
  about* the matrix with an LLM that has structural access. Single-trench
  workflows benefit modestly; multi-trench and corpus workflows benefit
  substantially.
- **6.2 Provenance as a first-class design constraint.** Argue that the
  changelog is what makes LLM editing acceptable in a discipline whose
  central methodological commitment is to traceable interpretation.
- **6.3 Comparison with prior digital tooling.** A short table: HMC,
  ArchEd, Stratify, gvSIG, ad-hoc scripts, `harris-mcp`. Axes: open
  format, multi-doc, programmatic access, LLM-native, provenance,
  rendering, validation.
- **6.4 Risks.** Hallucinated correspondences with high-sounding
  rationales; subtle structural edits that pass validation but distort
  meaning; over-reliance on the LLM's narrative summary at the expense of
  reading the diagram. Mitigations: mandatory `note` field, default-on
  diff display in clients, recommended human review checkpoint.
- **6.5 Standards politics.** A frank paragraph on HMC/HMCX as a closed
  de facto standard, and on HMDP as a deliberate small open alternative —
  not a competitor, an *escape hatch*.

## 7. Limitations

- HMC/HMCX are read-only (GraphML payload and CSV export); other HMC
  variants fall back to a best-effort reader.
- The reconciliation evaluation (§5.4) uses synthetic descriptions, one
  site, and team vocabularies that share period and type names.
- No automatic phase inference; the LLM proposes, the human (or the LLM
  under instruction) commits.
- Validation does not check archaeological plausibility (e.g., a cut
  predating its fill is structurally legal but semantically odd).
- Single-process, in-memory; not designed for concurrent multi-user
  editing.

## 8. Future work

- Reverse-engineered or partner-supplied HMC/HMCX read/write.
- Spatial coreference: use context geometries to suggest correspondences
  across trenches.
- Bibliographic linkage to `ohmi` (Zotero-backed).
- Persistent storage in Mongo with a per-matrix versioned history.
- Evaluation methodology: how would one *measure* the quality of LLM
  interpretive assertions on a Harris matrix? Inter-rater agreement
  against expert archaeologists is the obvious baseline. §5.4 gives a
  ground-truth harness for the deterministic layer; the same harness can
  score an LLM (or a human) triaging `propose_reconciliation` output.

## 9. Conclusion

- Restate the contribution in one paragraph.
- Frame the broader claim: digital archaeology should treat LLMs as
  *another tool that needs structured access*, not as an oracle that
  consumes screenshots. MCP is one concrete way to provide that access;
  the Harris matrix is a useful first case because its semantics are
  unambiguous and its formats are messy.

---

## Appendix A — HMDP schema (informal)

Tabular spec of the JSON document: top-level keys (`name`, `profile`,
`contexts`, `relations`, `phases`, `periods`, `correspondences`,
`changelog`), with per-field type, required/optional, and a one-line
description.

## Appendix B — Tool & resource catalogue

Full list of MCP tools and resources exposed by the server, grouped by
read / write / cross-doc / output, with input/output schemas. Aimed at
the developer reader; cite repo for the source of truth.

## Appendix C — Worked example payloads

Verbatim JSON payloads from §5, for reproducibility.

---

## Notes to self while drafting

- Keep the LLM out of §§2–4 prose as much as possible; the server is the
  contribution, not the model behind it. The model is interchangeable.
- The reviewer who matters most is the archaeologist who has never heard
  of MCP. §1 and §6 must work for them. The reviewer who matters second
  most is the digital-humanities engineer who has never excavated. §3
  and §4 must work for them.
- Resist the temptation to benchmark "how good is GPT-4 at proposing
  correspondences" — that is a different paper, and it dates badly.
  The contribution here is the *substrate*.
- One figure per section, max. Architecture diagram (§3.1), changelog
  example (§3.6), worked-example diff (§5.2), reconciliation F1
  (§5.4, `sim/results/fig-reconcile-f1.pdf`), comparison table (§6.3).
