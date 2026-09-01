# -*- coding: utf-8 -*-
"""
GTEx v8 正常组织 median TPM 热图 (15 个 T 细胞耗竭相关基因)
1) 下载官方 median TPM gct 文件(如本地已有则跳过)
2) 提取 15 个基因 × 54 组织 的表达矩阵
3) 判定 广泛表达 / 免疫组织特异 / 选择性·低表达
4) 输出 gtex_heatmap.png (工作区根目录) + gtex_expression_matrix.csv
"""
import gzip
import os
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(WORKDIR, "gtex_data")
GCT_GZ = os.path.join(DATA_DIR, "GTEx_Analysis_2017-06-05_v8_RNASeQCv1.1.9_gene_median_tpm.gct.gz")
URL = ("https://storage.googleapis.com/adult-gtex/bulk-gex/v8/rna-seq/"
       "GTEx_Analysis_2017-06-05_v8_RNASeQCv1.1.9_gene_median_tpm.gct.gz")

# 免疫相关组织 (gct 实际列名, 空格格式)
IMMUNE_TISSUES = ["Whole Blood", "Spleen", "Cells - EBV-transformed lymphocytes"]


def setup_fonts():
    from matplotlib import font_manager
    for fp in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def download():
    if os.path.exists(GCT_GZ) and os.path.getsize(GCT_GZ) > 5_000_000:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = GCT_GZ + ".part"
    for attempt in range(4):
        try:
            with requests.get(URL, stream=True, timeout=120,
                              headers={"User-Agent": "BioDSH-demo"}) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
            os.replace(tmp, GCT_GZ)
            return
        except Exception as ex:
            print("download retry", attempt + 1, type(ex).__name__)
    raise RuntimeError("GTEx gct 下载失败")


def tissue_specificity_index(x):
    """tau: 0=全组织均一表达, 1=完全组织特异 (对 TPM 用 log1p 后计算)"""
    x = np.log1p(np.asarray(x, dtype=float))
    m = x.max()
    if m <= 0:
        return 0.0
    return float(np.mean(1.0 - x / m))


def main():
    with open(os.path.join(WORKDIR, "genes.txt"), encoding="utf-8") as f:
        genes = [ln.strip() for ln in f if ln.strip()]

    download()
    print("gct size:", os.path.getsize(GCT_GZ))

    with gzip.open(GCT_GZ, "rt", encoding="utf-8") as f:
        _ = f.readline()
        _ = f.readline()
        header = f.readline().rstrip("\n").split("\t")
    df = pd.read_csv(GCT_GZ, sep="\t", skiprows=2, encoding="utf-8")
    df.columns = header
    print("shape:", df.shape)

    sub = df[df["Description"].isin(genes)].copy()
    missing = [g for g in genes if g not in set(sub["Description"])]
    print("匹配到:", len(sub), " 缺失:", missing)

    tissue_cols = [c for c in df.columns if c not in ("Name", "Description")]
    mat = sub.set_index("Description")[tissue_cols].astype(float)
    mat = mat.reindex(genes)
    mat.columns = [c.replace("_", " ") for c in mat.columns]

    # ---- 免疫组织列 ----
    # 分类统计只用正常免疫组织(血液+脾); EBV 细胞系仅参与热图左侧排序与着色
    imm_norm = ["Whole Blood", "Spleen"]
    imm_cols_all = [c for c in mat.columns if c in IMMUNE_TISSUES]
    imm_cols = [c for c in mat.columns if c in imm_norm]
    print("免疫组织列(着色):", imm_cols_all, "| 分类用:", imm_cols)

    # ---- 诊断指标 ----
    non_cols = [c for c in mat.columns if c not in imm_cols]
    imm_mean = mat[imm_cols].mean(axis=1)
    non_mean = mat[non_cols].mean(axis=1)
    frac_expr = (mat >= 1).mean(axis=1)
    tau = mat.apply(tissue_specificity_index, axis=1)
    top3 = mat.apply(lambda r: "; ".join(
        f"{t}={v:g}" for t, v in r.nlargest(3).items()), axis=1)

    # ---- 分类 ----
    def classify(g):
        if imm_mean[g] >= 2 and imm_mean[g] >= 3 * non_mean[g]:
            return "immune"          # 免疫组织特异(富集)
        if frac_expr[g] >= 0.7:
            return "broad"           # 全身广泛表达
        return "low"                 # 选择性/低表达

    cls = [classify(g) for g in genes]
    diag = pd.DataFrame({
        "基因": genes, "分类": cls,
        "免疫组织均TPM": imm_mean.round(1), "其他组织均TPM": non_mean.round(1),
        "富集倍数": (imm_mean / non_mean).round(1),
        "TPM>=1组织%": (frac_expr * 100).round(0), "tau": tau.round(2),
        "最高表达组织": top3})
    diag.to_csv(os.path.join(WORKDIR, "gtex_gene_classification.csv"),
                index=False, encoding="utf-8-sig")
    print(diag.to_string(index=False))

    setup_fonts()

    # ---- 热图 ----
    imm_now = [c for c in mat.columns if c in imm_cols_all]
    others = [c for c in mat.columns if c not in imm_now]
    mat2 = mat[imm_now + others]                 # 免疫相关组织排最左
    is_imm = [1 if c in imm_now else 0 for c in mat2.columns]

    data = np.log1p(mat2.values)
    order = []
    for c in ["immune", "broad", "low"]:
        idx = [i for i, x in enumerate(cls) if x == c]
        idx.sort(key=lambda i: -mat2.values[i].max())
        order.extend(idx)
    data = data[order]
    row_cls = [cls[i] for i in order]
    row_labels = [mat2.index[i] for i in order]

    gene_cmap = {"immune": "#C0392B", "broad": "#27AE60", "low": "#7F8C8D"}
    n_col = len(mat2.columns)

    fig = plt.figure(figsize=(17, 8.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[0.55, 12], hspace=0.06,
                          left=0.15, right=0.99, top=0.93, bottom=0.30)
    ax0 = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[1], sharex=ax0)

    ax0.imshow([is_imm], aspect="auto", cmap=ListedColormap(["#D5D8DC", "#C0392B"]),
               vmin=0, vmax=1, extent=[0, n_col, 0, 1])
    ax0.set_yticks([])
    ax0.set_xlim(0, n_col)
    ax0.tick_params(axis="x", bottom=False, labelbottom=False)

    ax1.imshow(data, aspect="auto", cmap="YlOrRd", vmin=0, vmax=6)
    ax1.set_yticks(range(len(row_labels)))
    ticks = ax1.set_yticklabels(row_labels, fontsize=11, fontweight="bold")
    for t, c in zip(ticks, [gene_cmap[x] for x in row_cls]):
        t.set_color(c)
    ax1.set_xticks(np.arange(n_col) + 0.5)
    ax1.set_xticklabels(mat2.columns, rotation=90, fontsize=6.5)
    ax1.set_xlim(0, n_col)

    cbar = fig.colorbar(ax1.images[0], ax=[ax0, ax1], fraction=0.025, pad=0.01)
    cbar.set_label("median TPM (log1p)", fontsize=9)

    ax0.legend(handles=[Patch(color="#C0392B", label="免疫相关组织 (血液/脾/EBV淋巴细胞)"),
                        Patch(color="#D5D8DC", label="其他正常组织")],
               loc="upper left", bbox_to_anchor=(0, 1.35), ncol=2,
               fontsize=9, frameon=False)
    ax1.legend(handles=[Patch(color="#C0392B", label="免疫组织特异/富集"),
                        Patch(color="#27AE60", label="全身广泛表达"),
                        Patch(color="#7F8C8D", label="选择性/低表达")],
               loc="lower left", bbox_to_anchor=(0, -0.12), ncol=3,
               fontsize=9, frameon=False)
    ax1.set_title("GTEx v8 正常组织 median TPM — T 细胞耗竭相关基因 (15 个)",
                  fontsize=13, pad=18)

    out_png = os.path.join(WORKDIR, "gtex_heatmap.png")
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    print("saved:", out_png)

    mat.to_csv(os.path.join(WORKDIR, "gtex_expression_matrix.csv"), encoding="utf-8-sig")


if __name__ == "__main__":
    main()
