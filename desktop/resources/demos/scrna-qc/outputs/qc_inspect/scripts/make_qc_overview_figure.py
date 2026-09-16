"""QC overview figure (violins + scatter) from scrna-inspect-qc cell_qc.csv.

Read-only: does not touch the source h5ad, only plots per-cell QC metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"
]
plt.rcParams["axes.unicode_minus"] = False

in_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/qc_inspect/cell_qc.csv")
out_png = Path(sys.argv[2]) if len(sys.argv) > 2 else in_csv.parent / "qc_overview.png"

qc = pd.read_csv(in_csv)
qc = qc.dropna(subset=["total_counts", "n_genes_by_counts"])
if "pct_counts_mt" not in qc.columns:
    qc["pct_counts_mt"] = 0.0
qc = qc.fillna({"pct_counts_mt": 0.0})

n_cells = len(qc)
log_counts = np.log10(qc["total_counts"].values + 1.0)

fig, axes = plt.subplots(2, 2, figsize=(13, 9.5))
fig.suptitle(
    f"单细胞质控概览 (n = {n_cells} cells) — 只体检，未过滤", fontsize=15, y=0.99
)

panels = [
    (axes[0, 0], qc["n_genes_by_counts"].values, "每个细胞检出的基因数",
     "检出的基因数 (n_genes)", "#4C72B0"),
    (axes[0, 1], log_counts, "每个细胞的总 UMI 数 (log10)",
     "总 UMI 数 (log10)", "#55A868"),
    (axes[1, 0], qc["pct_counts_mt"].values, "每个细胞的线粒体基因比例 (%)",
     "线粒体基因比例 %", "#C44E52"),
]

for ax, values, title, ylabel, color in panels:
    vp = ax.violinplot([values], showmedians=False, widths=0.85)
    for body in vp["bodies"]:
        body.set_facecolor(color)
        body.set_alpha(0.55)
        body.set_edgecolor("none")
    for part in ("cbars", "cmins", "cmaxes"):
        vp[part].set_color("#333333")
        vp[part].set_linewidth(0.8)
    # median marker
    med = float(np.median(values))
    ax.plot(1, med, "o", color="#222222", ms=5, zorder=5)
    ax.text(1.12, med, f"中位数 {med:g}", va="center", fontsize=9)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticks([])
    ax.set_xlim(0.35, 1.85)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.set_axisbelow(True)

# --- scatter: total_counts (x, log10) vs n_genes (y), colored by mt% ---
ax = axes[1, 1]
sc = ax.scatter(
    log_counts,
    qc["n_genes_by_counts"].values,
    c=qc["pct_counts_mt"].values,
    cmap="RdYlBu_r",
    vmin=0,
    vmax=20,
    s=7,
    alpha=0.7,
    linewidths=0,
)
ax.axhline(200, color="grey", ls="--", lw=0.9)
ax.text(log_counts.max() * 0.98, 200, "建议最少 200 基因", fontsize=8, va="bottom",
        ha="right", color="grey")
ax.axhline(6000, color="grey", ls="--", lw=0.9)
ax.text(log_counts.max() * 0.98, 6000, "建议最多 6000 基因", fontsize=8, va="top",
        ha="right", color="grey")
ax.set_xlabel("总 UMI 数 (log10)", fontsize=10)
ax.set_ylabel("检出的基因数", fontsize=10)
ax.set_title("总 UMI 数 vs 基因数，颜色=线粒体比例", fontsize=11)
ax.grid(alpha=0.25, lw=0.5)
ax.set_axisbelow(True)
cbar = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
cbar.set_label("线粒体基因比例 %（>20% 同色最深）", fontsize=9)
cbar.ax.tick_params(labelsize=8)

fig.tight_layout(rect=(0, 0, 1, 0.965))
out_png.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out_png, dpi=160)
fig.savefig(out_png.with_suffix(".svg"))
plt.close(fig)
print(f"figure written: {out_png.resolve()}")
