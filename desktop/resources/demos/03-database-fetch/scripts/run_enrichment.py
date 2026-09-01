# -*- coding: utf-8 -*-
"""
用 MSigDB Hallmark v7.5.1 (本地 gmt) 对 genes.txt 做超几何富集分析 (gseapy.enrichr, 全离线)
输出: enrichment_hallmark.csv, enrichment_barplot.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import gseapy as gp

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GMT = r"C:\Users\MOLIEX-DESKTOP\Documents\Project\BioDSH\competitors\OmicVerse\omicverse\datasets\data_files\h.all.v7.5.1.symbols.gmt"

with open(os.path.join(WORKDIR, "genes.txt"), encoding="utf-8") as f:
    genes = [ln.strip() for ln in f if ln.strip()]
print("输入基因 (%d):" % len(genes), ", ".join(genes))

res = gp.enrichr(gene_list=genes, gene_sets=GMT, organism="human",
                 outdir=None, no_plot=True, cutoff=1.0)
df = res.res2d.copy()
df = df.sort_values("Adjusted P-value").reset_index(drop=True)

keep = [c for c in ["Gene_set", "Term", "Overlap", "P-value", "Adjusted P-value",
                    "Odds Ratio", "Combined Score", "Genes"] if c in df.columns]
df[keep].to_csv(os.path.join(WORKDIR, "enrichment_hallmark.csv"),
                index=False, encoding="utf-8-sig")
print("\n=== 富集结果(全部) ===")
show = [c for c in ["Term", "Overlap", "P-value", "Adjusted P-value", "Odds Ratio"] if c in df.columns]
print(df[show].to_string(index=False))

# ---- 柱状图: 按校正后 p 值排序取前 10 ----
top = df.head(10).iloc[::-1].copy()          # 从下往上画, p 最小的在最上面
terms = [t.replace("HALLMARK_", "").replace("_", " ") for t in top["Term"]]
adjp = top["Adjusted P-value"].astype(float)
neglog = -np.log10(np.clip(adjp, 1e-300, None))
colors = ["#C0392B" if p < 0.05 else "#95A5A6" for p in adjp]

fig, ax = plt.subplots(figsize=(9, 6.5))
bars = ax.barh(range(len(terms)), neglog, color=colors, edgecolor="black", linewidth=0.5)
ax.set_yticks(range(len(terms)))
ax.set_yticklabels(terms, fontsize=9)
ax.set_xlabel("-log10 (adjusted P)", fontsize=11)
ax.set_title("MSigDB Hallmark gene sets enriched in T-cell exhaustion genes", fontsize=12)
ax.axvline(-np.log10(0.05), color="grey", linestyle="--", linewidth=1)
ax.text(-np.log10(0.05), len(terms) - 0.3, "P=0.05", color="grey", fontsize=8, ha="right")

overlap = top["Overlap"].astype(str)
for i, (b, lab) in enumerate(zip(bars, overlap)):
    ax.text(b.get_width() + 0.05, i, lab, va="center", fontsize=8, color="#333333")

from matplotlib.patches import Patch
ax.legend(handles=[Patch(color="#C0392B", label="adjusted P < 0.05"),
                   Patch(color="#95A5A6", label="not significant")],
          loc="lower right", fontsize=9, frameon=False)
ax.set_xlim(0, max(neglog) * 1.18)
plt.tight_layout()
out_png = os.path.join(WORKDIR, "enrichment_barplot.png")
plt.savefig(out_png, dpi=150)
print("\n已保存:", out_png)
