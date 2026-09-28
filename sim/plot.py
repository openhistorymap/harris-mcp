"""Figure for the reconciliation simulation, from sim/results/summary.csv.

    python -m sim.plot sim/results

Writes fig-reconcile-f1.pdf (for LaTeX) and .svg: F1 against description
noise (relation dropout 0.1), one panel per overlap scenario, one line per
reconciler, mean ± sd over seeds.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Categorical slots validated together on white (CVD and normal-vision
# separation pass); aqua is under 3:1 contrast, so every line also has its
# own marker and dash pattern and is labelled directly.
STYLE = {
    "text": ("#2a78d6", "o", (0, (1, 1.5))),
    "+ period/type": ("#eb6834", "s", (0, (4, 2))),
    "+ cycle check": ("#1baf7a", "^", (0, (6, 2, 1, 2))),
    "+ structure": ("#4a3aa7", "D", "solid"),
}
TITLES = {"trench": "Trench overlap", "full": "Full re-recording"}
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3dd"


def main(results: Path) -> None:
    rows = list(csv.DictReader((results / "summary.csv").open()))
    rows = [r for r in rows if float(r["dropout"]) == 0.1]
    n = rows[0]["n"]

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
        "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42, "svg.fonttype": "path", "svg.hashsalt": "harris-mcp",
    })
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.7), sharey=True)
    for ax, overlap in zip(axes, ("trench", "full")):
        ends = []
        for method, (colour, marker, dash) in STYLE.items():
            pts = sorted((float(r["noise"]), float(r["f1_mean"]), float(r["f1_sd"]))
                         for r in rows if r["overlap"] == overlap and r["method"] == method)
            xs, ys, sds = zip(*pts)
            ax.errorbar(xs, ys, yerr=sds, color=colour, marker=marker, markersize=4.5, linewidth=1.5,
                        linestyle=dash, capsize=2, elinewidth=0.8, label=method,
                        markeredgecolor="white", markeredgewidth=0.6)
            ends.append([ys[-1], ys[-1], xs[-1], method])
        if overlap == "full":
            # Direct labels at the line ends, pushed apart so they never overlap.
            ends.sort()
            for prev, cur in zip(ends, ends[1:]):
                cur[1] = max(cur[1], prev[1] + 0.065)
            for y, label_y, x, method in ends:
                ax.annotate(method, (x, y), xytext=(x + 0.03, label_y), va="center",
                            fontsize=7, color=INK)
        ax.set_title(TITLES[overlap], fontsize=8.5, color=INK, loc="left")
        ax.set_xticks([0.0, 0.2, 0.4], ["0", "20%", "40%"])
        ax.set_xlim(-0.03, 0.43 if overlap == "trench" else 0.62)
        ax.set_xlabel("Description noise")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("F1 (same-as pairs)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=len(STYLE), frameon=False, fontsize=7,
               bbox_to_anchor=(0.5, 1.07))
    fig.text(0.99, 0.01, f"mean ± sd, {n} seed{'s' if n != '1' else ''}; relation dropout 10%",
             ha="right", fontsize=6.5, color=MUTED)
    fig.tight_layout()
    # No embedded dates, so regenerating from the same summary.csv gives the same bytes.
    for ext, meta in (("pdf", {"CreationDate": None}), ("svg", {"Date": None})):
        fig.savefig(results / f"fig-reconcile-f1.{ext}", bbox_inches="tight", metadata=meta)
    print(f"wrote {results}/fig-reconcile-f1.pdf, .svg")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "sim/results"))
