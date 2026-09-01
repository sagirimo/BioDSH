"""BioDSH 参考 skill：Scanpy 单细胞聚类（合成数据 demo）。"""

import argparse
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import anndata as ad
import scanpy as sc

warnings.filterwarnings("ignore", category=FutureWarning)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    X = rng.poisson(0.05, size=(600, 2000)).astype(np.float32)
    adata = ad.AnnData(X)
    adata.obs_names = [f"cell{i}" for i in range(adata.n_obs)]
    adata.var_names = [f"gene{i}" for i in range(adata.n_vars)]

    sc.pp.filter_cells(adata, min_genes=10)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=500)
    adata = adata[:, adata.var.highly_variable].copy()
    sc.pp.pca(adata, n_comps=30, random_state=args.seed)
    sc.pp.neighbors(adata, random_state=args.seed)
    sc.tl.leiden(adata, flavor="igraph", n_iterations=2, directed=False, random_state=args.seed)
    sc.tl.umap(adata, random_state=args.seed)

    n_cells = int(adata.n_obs)
    n_clusters = int(adata.obs["leiden"].nunique())
    clusters = adata.obs[["leiden"]].reset_index()
    clusters.columns = ["cell", "cluster"]
    clusters.to_csv(outdir / "clusters.csv", index=False)

    coords = adata.obsm["X_umap"]
    labels = adata.obs["leiden"].astype("category")
    fig, ax = plt.subplots(figsize=(5, 4))
    for cat in labels.cat.categories:
        mask = labels.values == cat
        ax.scatter(coords[mask, 0], coords[mask, 1], s=4, label=str(cat))
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.legend(markerscale=3, fontsize=6, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(outdir / "umap.png", dpi=150)
    plt.close(fig)

    summary = {
        "n_cells": n_cells,
        "n_clusters": n_clusters,
        "umap_shape": list(coords.shape),
        "outputs": ["clusters.csv", "umap.png", "summary.json"],
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SCANPY_SKILL_OK " + json.dumps(summary))


if __name__ == "__main__":
    main()
