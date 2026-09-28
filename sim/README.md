# Simulation: stratigraphic unit reconciliation

When two teams record overlapping parts of a site, which of their units are
the same unit? This simulation measures how well `harris-mcp`'s
`propose_reconciliation` answers that question, against a ground truth, and
what each of its ingredients contributes.

## Design

**Ground truth.** A real Harris matrix: Çatalhöyük East Mound, Buildings 1
and 5 (matrix by Craig Cessford; 705 units, 852 stratigraphic relations,
periods *Building 1* / *Building 5* / *Outside*), from T. S. Dye's hm
examples at commit `9229fa7`. The source carries no unit descriptions, so
each unit gets a hidden "true" description drawn from a small field
vocabulary: compaction, Munsell-like colour, texture and inclusions for
deposits; two shape terms for cuts.

**Two recording teams.**

| Scenario | Team A records | Team B records | Shared |
|---|---|---|---|
| `trench` | Building 1 + Outside | Building 5 + Outside | the 52 *Outside* units |
| `full` | everything | everything | all 705 units (legacy vs new record) |

Each team numbers its units independently (shuffled, so identifiers carry
no information) and describes every unit in its own words:

- **description noise** *p* — each ordinal attribute (colour, texture,
  compaction) drifts to an adjacent value with probability *p*; each
  inclusion is missed with probability *p* and a spurious one is added with
  probability *p*; each cut-shape term is replaced with probability *p*;
- **relation dropout** *d* — each true relation between recorded units is
  missed with probability *d*;
- **splits and lumps** (team B, shared units only, 5 % each) — a unit
  recorded as two superposed units, or two adjacent units recorded as one
  (only where that creates no cycle).

Scenarios: *p* ∈ {0, 0.2, 0.4} with *d* = 0.1, plus *p* = 0.4, *d* = 0.3;
10 seeds each.

**Reconcilers.** A cumulative ablation of `propose_reconciliation`, all
with description token-Jaccard candidates at threshold 0.3 and greedy 1:1
matching:

1. `text` — description similarity only (the server's behaviour before this
   work, via `cross_reference`);
2. `+ period/type` — only compare units with the same period and type;
3. `+ cycle check` — reject a match if merging the two matrices through it
   would place a unit both above and below another;
4. `+ structure` — add structural agreement to the score (the fraction of a
   unit's neighbours already matched to the candidate's neighbours on the
   same side, weight 0.5), re-matching over 3 rounds. This is the server's
   default.

**Scoring.** A pair (unit in A, unit in B) is true when the two record at
least one common true unit (so a split unit has two true partners, and one
1:1 matching cannot recover both). Precision, recall and F1 over pairs;
*contradicting units* = units caught in a cycle after merging both matrices
through the proposed matches, as reported by `check_correspondences`.

All reconciliation runs through the MCP tools over an in-memory client. For
seed 0 of every scenario the `+ structure` matches are also recorded with
`assert_correspondence` and confirmed contradiction-free by
`check_correspondences`.

## Reproduce

```bash
sh sim/fetch_data.sh                       # pinned + checksummed ground truth
docker build --target test -t harris-mcp:test .
docker run --rm -e HARRIS_MCP_COMMIT=$(git rev-parse --short HEAD) \
  -v "$PWD/sim/data:/data:ro" -v "$PWD/sim/results:/out" harris-mcp:test \
  sh -c "python -m sim.reconcile_sim --data /data/catalhoyuk-bldg-1-5 --out /out && python -m sim.plot /out"
```

About 30 minutes for 10 seeds. Runs are deterministic for a given seed.
Any loadable matrix can be the ground truth (`--data`); for the `trench`
scenario name the periods each team excavates with `--trench-a` /
`--trench-b`.

## Outputs (`sim/results/`)

| File | Content |
|---|---|
| `runs.csv` | one row per scenario × seed × reconciler: precision, recall, F1, contradicting units, sizes |
| `summary.csv` | mean and sd over seeds per scenario × reconciler |
| `summary.md`, `summary.tex` | the paper table (F1 mean ± sd, contradictions), Markdown and LaTeX (`booktabs`) |
| `fig-reconcile-f1.pdf`, `.svg` | F1 against description noise, one panel per scenario |
| `meta.json` | input checksums, seeds, parameters, package versions, commit, runtime |

## Caveats

- Descriptions are synthetic; real recording differs in vocabulary and in
  how errors correlate (a team that misreads colour does so consistently).
- Both teams use the same period names and unit types, which flatters the
  `+ period/type` filter; real teams rarely share a phasing vocabulary.
- Split and lump rates are fixed at 5 %; one 1:1 matching cannot represent
  a split, which caps recall.
- The ground truth is one site. The trench overlap (52 units, 17 relations
  to the rest of the site) is small.
