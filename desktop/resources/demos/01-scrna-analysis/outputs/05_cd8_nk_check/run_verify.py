# -*- coding: utf-8 -*-
"""
CD8 T vs NK 区分验证 + 高清 UMAP + 最终注释表导出
Outputs:
  04_results/umap_by_celltype_300dpi.png   300dpi UMAP（PPT 用）
  04_results/final_cell_annotation.csv     最终注释表（中文列名，Excel 直接打开）
  05_cd8_nk_check/cd8_nk_umap_panel.png    区分基因在 UMAP 上的表达图（300dpi）
  05_cd8_nk_check/cd8_nk_dotplot.png       区分基因 × 9 个簇 点图（300dpi）
  05_cd8_nk_check/cd8_nk_marker_evidence.csv  各簇表达证据表（均值 + 阳性率）
"""
import pathlib
import numpy as np
import pandas as pd
import scanpy as sc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

for f in ["Microsoft YaHei", "SimHei", "Arial"]:
    if f in matplotlib.font_manager.get_font_names():
        matplotlib.rcParams["font.sans-serif"] = [f]
        break
matplotlib.rcParams["axes.unicode_minus"] = False
sc.settings.verbosity = 1

WS = pathlib.Path(r"C:\Users\MOLIEX-DESKTOP\BioDSH\demos\01-scrna-analysis")
OUT4 = WS / "outputs" / "04_results"
OUT5 = WS / "outputs" / "05_cd8_nk_check"
OUT5.mkdir(parents=True, exist_ok=True)

BROAD_CN = {
    "T_cell": "T 细胞", "NK_cell": "NK 细胞", "B_cell": "B 细胞",
    "plasma_cell": "浆细胞", "myeloid": "单核/髓系细胞",
    "dendritic": "树突状细胞", "unknown": "未定细胞",
}
TSTATE_CN = {
    "naive_memory": "初始/记忆型", "cytotoxic": "细胞毒性型", "exhaustion": "耗竭型",
    "regulatory": "调节型", "cycling": "增殖型", "interferon": "干扰素应答型",
    "activation": "活化型", "not_applicable": "不适用", "nan": "不适用",
}

adata = sc.read_h5ad(WS / "outputs" / "03_annotation" / "annotated.h5ad")
adata.obs["cell_type"] = [BROAD_CN.get(x, x) for x in adata.obs["biodsh_broad_label"].astype(str)]
adata.obs["t_state_cn"] = [
    TSTATE_CN.get(str(x).replace("nan", "nan"), "不适用")
    for x in adata.obs["biodsh_t_state"].astype(str)
]
order = [v for v in BROAD_CN.values() if v in set(adata.obs["cell_type"])]
adata.obs["cell_type"] = pd.Categorical(adata.obs["cell_type"], categories=order)

# ---------- 1. 高清 UMAP（300 dpi，PPT 用） ----------
fig, ax = plt.subplots(figsize=(8.2, 6.6))
sc.pl.umap(adata, color="cell_type", ax=ax, show=False, size=14,
           title="人外周血单个核细胞 UMAP（按细胞类型）",
           legend_loc="right margin", frameon=False)
fig.savefig(OUT4 / "umap_by_celltype_300dpi.png", dpi=300, bbox_inches="tight")
plt.close(fig)
print("saved umap_by_celltype_300dpi.png")

# ---------- 2. 最终注释表 ----------
tab = pd.DataFrame({
    "细胞编号": adata.obs_names.astype(str),
    "Leiden簇": adata.obs["leiden"].astype(str),
    "细胞类型": adata.obs["cell_type"].astype(str),
    "T细胞状态": adata.obs["t_state_cn"].astype(str),
})
tab["UMAP_1"] = np.asarray(adata.obsm["X_umap"])[:, 0].round(4)
tab["UMAP_2"] = np.asarray(adata.obsm["X_umap"])[:, 1].round(4)
tab.to_csv(OUT4 / "final_cell_annotation.csv", index=False, encoding="utf-8-sig")
print("saved final_cell_annotation.csv (%d rows)" % len(tab))

# ---------- 3. CD8 T vs NK 区分验证 ----------
MARKERS = ["CD3D", "CD3E", "CD8A", "CD8B", "NKG7", "GNLY", "KLRD1", "KLRF1", "NCAM1"]
present = [g for g in MARKERS if g in adata.var_names]
missing = [g for g in MARKERS if g not in adata.var_names]
print("present:", present, "| missing:", missing)

# 3a. 区分基因在 UMAP 上的表达图（每格一个基因，越亮表达越高）
sc.pl.umap(adata, color=present, ncols=3, show=False, size=10,
           vmin=0, frameon=False, cmap="magma")
plt.savefig(OUT5 / "cd8_nk_umap_panel.png", dpi=300, bbox_inches="tight")
plt.close("all")
print("saved cd8_nk_umap_panel.png")

# 3b. 点图：9 个簇 × 区分基因
sc.pl.dotplot(adata, present, groupby="leiden", standard_scale="var",
              show=False, title="CD8 T / NK 区分基因表达（按 Leiden 簇）")
plt.savefig(OUT5 / "cd8_nk_dotplot.png", dpi=300, bbox_inches="tight")
plt.close("all")
print("saved cd8_nk_dotplot.png")

# 3c. 表达证据表：簇 0（细胞毒性 T/CD8）、4（NK）、1/5（初始/记忆 T）对比
X = adata[:, present].X
if hasattr(X, "toarray"):
    X = X.toarray()
expr = pd.DataFrame(X, index=adata.obs_names, columns=present)
focus = adata.obs[["leiden", "cell_type", "t_state_cn"]].copy()
focus["簇"] = "簇" + focus["leiden"].astype(str)

rows = []
for cl, name in [("0", "簇0 细胞毒性 T(疑CD8)"), ("4", "簇4 NK"),
                 ("1", "簇1 初始/记忆 T"), ("5", "簇5 初始/记忆 T")]:
    m = focus["leiden"] == cl
    sub = expr.loc[m]
    for g in present:
        vec = sub[g].to_numpy()
        rows.append({
            "簇": cl, "细胞类型/状态": name,
            "基因": g,
            "平均表达量(log归一化)": round(float(vec.mean()), 3),
            "阳性细胞比例(%)": round(float((vec > 0).mean()) * 100, 1),
        })
ev = pd.DataFrame(rows)
ev.to_csv(OUT5 / "cd8_nk_marker_evidence.csv", index=False, encoding="utf-8-sig")
print("saved cd8_nk_marker_evidence.csv")

# 3d. 简明判断文本
def rep(cl):
    sub = ev[ev["簇"] == cl].set_index("基因")["阳性细胞比例(%)"]
    return sub

for cl, label in [("0", "簇0(细胞毒性T)"), ("4", "簇4(NK)")]:
    s = rep(cl)
    print("\n--- %s ---" % label)
    print("CD3D+ %.1f%%  CD3E+ %.1f%%  CD8A+ %.1f%%  CD8B+ %.1f%%" % (
        s["CD3D"], s["CD3E"], s["CD8A"], s["CD8B"]))
    print("NKG7+ %.1f%%  GNLY+ %.1f%%  KLRD1+ %.1f%%  KLRF1+ %.1f%%  NCAM1+ %.1f%%" % (
        s["NKG7"], s["GNLY"], s["KLRD1"], s["KLRF1"], s["NCAM1"]))

print("\nDONE")
