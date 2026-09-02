"""In-silico single-gene knockout for scRNA-seq, scTenifoldKnk-style.

This is a self-contained Python reimplementation of the *scTenifoldKnk* concept
(Osorio et al.; built on scTenifoldNet). It does NOT wrap the R package; it uses
only the BioDSH analysis environment (numpy, scipy, pandas, scanpy, anndata,
matplotlib, scikit-learn).

Pipeline
--------
1. Load an .h5ad (READ-ONLY). If the matrix looks like raw counts, library-size
   normalize + log1p. Select the top-N highly variable genes, always forcing the
   target gene in. Work on a dense cells x genes matrix over those genes.
2. Build a wild-type gene regulatory network (GRN) ``A_wt`` with pcNet
   (principal-component regression): for each gene g, regress its expression on
   the top principal components of the OTHER genes; the regression coefficients
   (mapped back to gene space) are g's incoming edges. Assemble the genes x genes
   weighted adjacency, symmetrize, and scale to [-1, 1] by the max absolute value
   (as scTenifoldNet does).
3. Knock out the target gene: copy ``A_wt`` -> ``A_ko`` and zero the target gene's
   row AND column (its regulatory influence, incoming and outgoing, is removed).
4. Compare ``A_wt`` vs ``A_ko`` by manifold alignment: embed each network with the
   leading eigenvectors of its normalized Laplacian, align the two embeddings with
   orthogonal Procrustes, and take the per-gene Euclidean distance between the WT
   and KO aligned coordinates.
5. Rank genes by that distance (larger = more affected by the knockout). Assign
   significance the scTenifoldKnk way: Box-Cox transform the distances, then a
   normal upper-tail p-value, then Benjamini-Hochberg FDR.
6. Write ``virtual_ko_ranked.csv``, ``virtual_ko_top_genes.png``,
   ``virtual_ko_summary.json`` to --outdir and print a short summary.

The reference / canonical method is the R package **scTenifoldKnk** (and
**scTenifoldNet**); prefer it for publication-grade work if R is available.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scanpy as sc
from scipy import sparse, stats
from sklearn.decomposition import PCA


# --------------------------------------------------------------------------- #
# Data loading / preprocessing
# --------------------------------------------------------------------------- #
def _looks_like_counts(x: np.ndarray) -> bool:
    """Heuristic: raw counts are non-negative integers."""
    if x.size == 0:
        return False
    sample = x[: min(x.shape[0], 2000)]
    if np.any(sample < 0):
        return False
    # if all sampled values are (near) integers, treat as counts
    return bool(np.allclose(sample, np.round(sample)))


def _resolve_gene(adata, gene: str) -> str:
    """Return the exact var_name for ``gene`` or raise with suggestions."""
    names = list(adata.var_names)
    if gene in names:
        return gene
    lower = {n.lower(): n for n in names}
    if gene.lower() in lower:
        return lower[gene.lower()]
    # suggest similar names (substring / shared prefix)
    g = gene.lower()
    similar = [n for n in names if g in n.lower() or n.lower() in g]
    if not similar:
        similar = [n for n in names if n.lower().startswith(g[:3])][:10]
    hint = ", ".join(similar[:10]) if similar else "(no similar names found)"
    raise SystemExit(
        f"ERROR: gene '{gene}' not found in the dataset "
        f"({adata.n_vars} genes). Similar names: {hint}"
    )


def load_and_prepare(input_path: str, gene: str, n_hvg: int, seed: int):
    """Load h5ad read-only, normalize if needed, pick HVGs (+target gene).

    Returns (X_dense[cells x genes], gene_list, target_name, n_cells_total).
    """
    adata = sc.read_h5ad(input_path)  # read-only; we never write it back
    n_cells_total = adata.n_obs
    target = _resolve_gene(adata, gene)

    # normalize only if the data still look like raw counts
    X0 = adata.X
    probe = (X0[:10].toarray() if sparse.issparse(X0) else np.asarray(X0[:10])).ravel()
    if _looks_like_counts(probe):
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)

    # pick highly variable genes to cap network size; always keep the target
    n_hvg = int(min(n_hvg, adata.n_vars))
    try:
        sc.pp.highly_variable_genes(adata, n_top_genes=n_hvg, flavor="seurat")
        hvg_mask = adata.var["highly_variable"].to_numpy()
    except Exception:
        # fallback: rank by variance if the scanpy HVG routine fails on tiny data
        Xtmp = adata.X.toarray() if sparse.issparse(adata.X) else np.asarray(adata.X)
        var = Xtmp.var(axis=0)
        hvg_mask = np.zeros(adata.n_vars, dtype=bool)
        hvg_mask[np.argsort(var)[::-1][:n_hvg]] = True

    genes = list(adata.var_names[hvg_mask])
    if target not in genes:
        genes.append(target)

    sub = adata[:, genes]
    X = sub.X.toarray() if sparse.issparse(sub.X) else np.asarray(sub.X, dtype=float)
    X = np.asarray(X, dtype=np.float64)
    return X, list(sub.var_names), target, n_cells_total


# --------------------------------------------------------------------------- #
# GRN construction: pcNet (principal-component regression)
# --------------------------------------------------------------------------- #
def pc_net(X: np.ndarray, n_comp: int = 5, seed: int = 0) -> np.ndarray:
    """Build a gene regulatory network via principal-component regression.

    For each target gene g, regress its (standardized) expression on the top
    principal components of all OTHER genes, then map the PC-space coefficients
    back to gene space. The resulting genes x genes matrix A has A[i, j] = the
    weighted influence of gene j on gene i (incoming edges of i). Follows the
    scTenifoldNet pcNet idea; we use sklearn PCA + closed-form least squares.

    Cells x genes matrix in; genes x genes adjacency out (scaled to [-1, 1]).
    """
    n_cells, n_genes = X.shape
    # standardize genes (columns) so coefficients are comparable
    Z = X - X.mean(axis=0, keepdims=True)
    sd = Z.std(axis=0, keepdims=True)
    sd[sd == 0] = 1.0
    Z = Z / sd

    # cap PCs: scTenifoldNet-style small number, bounded by data size
    n_comp = int(max(1, min(n_comp, n_cells - 1, n_genes - 1)))

    A = np.zeros((n_genes, n_genes), dtype=np.float64)
    for i in range(n_genes):
        others = np.delete(np.arange(n_genes), i)
        Xo = Z[:, others]
        # PCA of the other genes
        k = int(min(n_comp, Xo.shape[1], max(1, Xo.shape[0] - 1)))
        pca = PCA(n_components=k, random_state=seed)
        scores = pca.fit_transform(Xo)  # cells x k
        loadings = pca.components_  # k x (n_genes-1)
        y = Z[:, i]
        # least-squares regression of y on the PC scores
        beta, *_ = np.linalg.lstsq(scores, y, rcond=None)  # length k
        # map PC-space coefficients back to gene space: (n_genes-1,)
        gene_coef = loadings.T @ beta
        A[i, others] = gene_coef

    np.fill_diagonal(A, 0.0)
    # symmetrize (undirected co-regulation strength) and scale to [-1, 1]
    A = (A + A.T) / 2.0
    m = np.max(np.abs(A))
    if m > 0:
        A = A / m
    return A


# --------------------------------------------------------------------------- #
# Knockout + manifold alignment
# --------------------------------------------------------------------------- #
def knockout(A_wt: np.ndarray, idx: int) -> np.ndarray:
    """Zero the target gene's row AND column -> KO network."""
    A_ko = A_wt.copy()
    A_ko[idx, :] = 0.0
    A_ko[:, idx] = 0.0
    return A_ko


def _laplacian_embedding(A: np.ndarray, dim: int) -> np.ndarray:
    """Leading eigenvectors of the symmetric normalized Laplacian.

    We use |A| as edge weights (both activation and repression are 'coupling'),
    build L_sym = I - D^-1/2 W D^-1/2, and take the eigenvectors with the
    smallest eigenvalues (the smooth manifold coordinates). Returns genes x dim.
    """
    W = np.abs(A)
    d = W.sum(axis=1)
    d_inv_sqrt = np.zeros_like(d)
    nz = d > 0
    d_inv_sqrt[nz] = 1.0 / np.sqrt(d[nz])
    Dm = np.diag(d_inv_sqrt)
    L = np.eye(A.shape[0]) - Dm @ W @ Dm
    L = (L + L.T) / 2.0  # enforce symmetry against numerical drift
    vals, vecs = np.linalg.eigh(L)
    order = np.argsort(vals)  # ascending; smallest = smoothest
    dim = int(min(dim, vecs.shape[1]))
    return vecs[:, order[:dim]]


def manifold_align_distance(A_wt: np.ndarray, A_ko: np.ndarray, dim: int = 30):
    """Per-gene WT<->KO distance via aligned Laplacian embeddings.

    Embed each network, align KO onto WT with orthogonal Procrustes (removes the
    arbitrary sign/rotation of eigenvectors), then take per-gene Euclidean
    distance between WT and aligned-KO coordinates. This is a robust, dependency-
    light stand-in for scTenifoldKnk's tensor / manifold-alignment step.
    """
    dim = int(min(dim, A_wt.shape[0] - 1)) if A_wt.shape[0] > 1 else 1
    E_wt = _laplacian_embedding(A_wt, dim)
    E_ko = _laplacian_embedding(A_ko, dim)
    # match dims (eigh could return fewer on degenerate cases)
    d = min(E_wt.shape[1], E_ko.shape[1])
    E_wt, E_ko = E_wt[:, :d], E_ko[:, :d]
    # orthogonal Procrustes: find R minimizing ||E_ko R - E_wt||
    M = E_ko.T @ E_wt
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    E_ko_aligned = E_ko @ R
    dist = np.sqrt(((E_wt - E_ko_aligned) ** 2).sum(axis=1))
    return dist


# --------------------------------------------------------------------------- #
# Significance: Box-Cox -> normal tail -> BH-FDR (scTenifoldKnk scheme)
# --------------------------------------------------------------------------- #
def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    n = len(pvals)
    order = np.argsort(pvals)
    ranked = pvals[order] * n / (np.arange(n) + 1)
    # enforce monotonicity from the largest p downward
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n, dtype=float)
    out[order] = np.clip(ranked, 0, 1)
    return out


def significance(dist: np.ndarray):
    """Return (pvalues, fdr) using a Box-Cox transform + normal upper tail.

    scTenifoldKnk models the (positive) distances with a Box-Cox transform to
    approximate normality, then flags genes in the upper tail. We standardize the
    transformed distances and take a one-sided normal p-value, then BH-FDR.
    """
    d = np.asarray(dist, dtype=float)
    shifted = d - d.min() + 1e-9  # Box-Cox needs strictly positive input
    try:
        if np.allclose(shifted, shifted[0]):
            raise ValueError("degenerate distances")
        transformed, _ = stats.boxcox(shifted)
    except Exception:
        # fall back to raw distances if Box-Cox cannot fit (e.g. tiny/degenerate)
        transformed = d
    mu = np.mean(transformed)
    sd = np.std(transformed)
    if sd == 0:
        pvals = np.ones_like(transformed)
    else:
        z = (transformed - mu) / sd
        pvals = stats.norm.sf(z)  # upper tail: larger distance -> smaller p
    fdr = _bh_fdr(pvals)
    return pvals, fdr


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
def write_outputs(outdir: Path, df, target, n_cells, n_genes, n_hvg, seed):
    import pandas as pd  # local import keeps top-level import light

    outdir.mkdir(parents=True, exist_ok=True)
    ranked_csv = outdir / "virtual_ko_ranked.csv"
    df.to_csv(ranked_csv, index=False)

    # barplot of the top ~20 affected genes (exclude the target itself, which is
    # trivially perturbed since we zeroed its edges)
    top = df[df["gene"] != target].head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.barh(top["gene"], top["distance"], color="#c0392b")
    ax.set_xlabel("WT<->KO aligned distance (larger = more affected)")
    ax.set_title(f"Top genes affected by virtual knockout of {target}")
    fig.tight_layout()
    png = outdir / "virtual_ko_top_genes.png"
    fig.savefig(png, dpi=150)
    plt.close(fig)

    n_sig = int((df["FDR"] < 0.05).sum())
    top10 = df[df["gene"] != target].head(10)["gene"].tolist()
    summary = {
        "target_gene": target,
        "n_cells": int(n_cells),
        "n_genes_used": int(n_genes),
        "n_significant_fdr_0.05": n_sig,
        "top10_affected_genes": top10,
        "params": {"n_hvg": int(n_hvg), "seed": int(seed)},
        "method": "scTenifoldKnk-style pcNet GRN + manifold-alignment KO (Python reimplementation)",
        "reference": "scTenifoldKnk / scTenifoldNet (Osorio et al.)",
    }
    summ_json = outdir / "virtual_ko_summary.json"
    summ_json.write_text(json.dumps(summary, indent=2))
    return ranked_csv, png, summ_json, n_sig, top10


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="In-silico single-gene knockout for scRNA-seq (scTenifoldKnk-style)."
    )
    parser.add_argument("--input", required=True, help="Input .h5ad (read-only).")
    parser.add_argument("--gene", required=True, help="Target gene symbol to knock out.")
    parser.add_argument(
        "--outdir",
        default="virtual_knockout_out",
        help="Output directory (default: virtual_knockout_out).",
    )
    parser.add_argument(
        "--n-hvg",
        type=int,
        default=2000,
        help="Cap the network to the top N highly variable genes (default 2000).",
    )
    parser.add_argument(
        "--n-pc",
        type=int,
        default=5,
        help="PCs per gene for pcNet regression (default 5; capped 3-10-ish).",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default 0).")
    args = parser.parse_args()

    import pandas as pd

    np.random.seed(args.seed)
    outdir = Path(args.outdir)

    print(f"[virtual-ko] loading {args.input} (read-only) ...")
    X, genes, target, n_cells_total = load_and_prepare(
        args.input, args.gene, args.n_hvg, args.seed
    )
    n_cells, n_genes = X.shape
    print(f"[virtual-ko] {n_cells} cells x {n_genes} genes; target = {target}")

    if n_genes < 3 or n_cells < 3:
        raise SystemExit(
            "ERROR: dataset too small after HVG selection "
            f"({n_cells} cells x {n_genes} genes) to build a network."
        )

    n_pc = int(max(3, min(args.n_pc, 10)))
    print(f"[virtual-ko] building WT gene regulatory network (pcNet, {n_pc} PCs) ...")
    A_wt = pc_net(X, n_comp=n_pc, seed=args.seed)

    idx = genes.index(target)
    print(f"[virtual-ko] knocking out {target} (zeroing its row + column) ...")
    A_ko = knockout(A_wt, idx)

    print("[virtual-ko] manifold alignment (Laplacian embedding + Procrustes) ...")
    dist = manifold_align_distance(A_wt, A_ko)

    pvals, fdr = significance(dist)
    df = pd.DataFrame(
        {"gene": genes, "distance": dist, "pvalue": pvals, "FDR": fdr}
    ).sort_values("distance", ascending=False, kind="mergesort").reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))
    # reorder columns
    df = df[["gene", "distance", "pvalue", "FDR", "rank"]]

    ranked_csv, png, summ_json, n_sig, top10 = write_outputs(
        outdir, df, target, n_cells, n_genes, args.n_hvg, args.seed
    )

    print("\n===== virtual knockout summary =====")
    print(f"target gene       : {target}")
    print(f"cells x genes     : {n_cells} x {n_genes} (of {n_cells_total} total cells)")
    print(f"significant (FDR<0.05, excl. target) : {n_sig}")
    print(f"top affected genes: {', '.join(top10)}")
    print(f"\noutputs written to {outdir}/:")
    print(f"  - {ranked_csv.name}")
    print(f"  - {png.name}")
    print(f"  - {summ_json.name}")


if __name__ == "__main__":
    main()
