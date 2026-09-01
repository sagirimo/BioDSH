# -*- coding: utf-8 -*-
"""
Final figure & table generation for pbmc3k analysis.
Reads annotated.h5ad (from scrna-cellstate-annotation skill) and produces:
  - umap_by_celltype.png        : UMAP colored by annotated cell type (Chinese labels)
  - marker_dotplot.png          : dot plot of canonical marker genes per cell type
  - celltype_proportions.csv    : cell-type proportion table
  - celltype_proportions.png    : proportion bar chart
  - celltype_proportions.txt    : human-readable proportion summary
"""
import sys
import pathlib
import numpy as np
import pandas as pd
import scanpy as sc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Chinese font support on Windows
for f in ["Microsoft YaHei", "SimHei", "Arial"]:
    if f in matplotlib.font_manager.get_font_names():
        matplotlib.rcParams["font.sans-serif"] = [f]
        break
matplotlib.rcParams["axes.unicode_minus"] = False
sc.settings.verbosity = 1

OUT = pathlib.Path(__file__).resolve().parent
ANNOT = OUT.parent / "03_annotation" / "annotated.h5ad"

BROAD_CN = {
    "T_cell": "T 细胞",
    "NK_cell": "NK 细胞",
    "B_cell": "B 细胞",
    "plasma_cell": "浆细胞",
    "myeloid": "单核/髓系细胞",
    "dendritic": "树突状细胞",
    "unknown": "未定细胞",
}

MARKERS = {
    "T 细胞": ["CD3D", "CD3E", "TRAC", "CD247"],
    "NK 细胞": ["NKG7", "GNLY", "KLRD1", "FCGR3A"],
    "B 细胞": ["MS4A1", "CD79A", "CD74", "HLA-DRA"],
    "浆细胞": ["MZB1", "JCHAIN", "SDC1", "IGHG1"],
    "单核/髓系": ["LST1", "TYROBP", "FCER1G", "CTSS"],
    "树突状细胞": ["FCER1A", "CD1C", "CLEC10A", "CST3"],
}

print("loading annotated.h5ad ...")
adata = sc.read_h5ad(ANNOT)

# ---- cell type column (Chinese labels) ----
raw = adata.obs["biodsh_broad_label"].astype(str)
adata.obs["cell_type"] = [BROAD_CN.get(x, x) for x in raw]
order = [BROAD_CN[k] for k in BROAD_CN if BROAD_CN[k] in set(adata.obs["cell_type"])]
adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"], categories=order)

# ---- 1. UMAP colored by cell type ----
fig, ax = plt.subplots(figsize=(7.2, 6.0))
sc.pl.umap(adata, color="cell_type", ax=ax, show=False, size=12,
           title="单细胞 UMAP（按细胞类型着色）",
           legend_loc="right margin", frameon=False)
fig.savefig(OUT / "umap_by_celltype.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("saved umap_by_celltype.png")

# ---- 2. marker dot plot ----
markers_present = {k: [g for g in v if g in adata.var_names] for k, v in MARKERS.items()}
markers_present = {k: v for k, v in markers_present.items() if v}
if markers_present:
    sc.pl.dotplot(adata, markers_present, groupby="cell_type",
                  standard_scale="var", show=False,
                  title="各细胞类型 marker 基因表达点图")
    plt.savefig(OUT / "marker_dotplot.png", dpi=200, bbox_inches="tight")
    plt.close("all")
    print("saved marker_dotplot.png")
else:
    print("WARNING: no marker genes found in dataset; skip dotplot")

# ---- 3. proportion table + chart ----
prop = adata.obs["cell_type"].value_counts().rename_axis("cell_type").reset_index()
prop.columns = ["cell_type", "n_cells"]
prop["percentage"] = (prop["n_cells"] / prop["n_cells"].sum() * 100).round(2)
prop = prop.sort_values("n_cells", ascending=False).reset_index(drop=True)
prop.to_csv(OUT / "celltype_proportions.csv", index=False)
with open(OUT / "celltype_proportions.txt", "w", encoding="utf-8") as fh:
    fh.write("细胞类型比例表（pbmc3k，共 %d 个细胞）\n" % prop["n_cells"].sum())
    fh.write("=" * 46 + "\n")
    for _, r in prop.iterrows():
        fh.write("%-12s %6d 个  %6.2f%%\n" % (r["cell_type"], r["n_cells"], r["percentage"]))
print("saved celltype_proportions.csv / .txt")

fig, ax = plt.subplots(figsize=(7.0, 5.2))
colors = plt.get_cmap("tab20")(np.linspace(0, 1, len(prop)))
bars = ax.barh(prop["cell_type"][::-1], prop["percentage"][::-1], color=colors[::-1])
for b, p in zip(bars, prop["percentage"][::-1]):
    ax.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2,
            "%.1f%%" % p, va="center", fontsize=9)
ax.set_xlabel("占全部细胞的比例 (%)")
ax.set_title("各细胞类型比例")
ax.set_xlim(0, prop["percentage"].max() * 1.18)
fig.tight_layout()
fig.savefig(OUT / "celltype_proportions.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("saved celltype_proportions.png")

print("\nDONE. all outputs in:", OUT)
