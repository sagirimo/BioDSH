"""State-aware, deterministic preprocessing and clustering for AnnData inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse


MIN_GENES_PER_CELL = 200
MIN_CELLS_PER_GENE = 3
TARGET_SUM = 10_000.0
MAX_HVG = 2_000
MAX_PCS = 50
MAX_NEIGHBORS = 15
LEIDEN_RESOLUTION = 1.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stored_values(matrix) -> np.ndarray:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    return np.asarray(values)


def detect_matrix_state(adata: ad.AnnData) -> tuple[str, dict]:
    values = stored_values(adata.X)
    if values.size == 0:
        raise ValueError("empty_expression_matrix")
    if not np.isfinite(values).all():
        raise ValueError("nonfinite_expression_values")
    if np.any(values < 0):
        raise ValueError("negative_expression_values")

    integer_like_fraction = float(np.isclose(values, np.rint(values), atol=1e-6).mean())
    evidence = {
        "stored_values": int(values.size),
        "integer_like_fraction": integer_like_fraction,
        "log1p_metadata_present": isinstance(adata.uns.get("log1p"), dict),
    }
    if integer_like_fraction >= 0.99:
        return "raw_counts", evidence
    if evidence["log1p_metadata_present"]:
        return "explicit_log1p", evidence
    raise ValueError("ambiguous_continuous_matrix_without_log1p_metadata")


def package_versions() -> dict[str, str]:
    names = ["anndata", "scanpy", "numpy", "pandas", "scipy", "igraph", "leidenalg"]
    return {name: importlib.metadata.version(name) for name in names}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    input_hash_before = sha256(input_path)

    adata = ad.read_h5ad(input_path)
    if adata.n_obs < 3 or adata.n_vars < 3:
        raise ValueError("matrix_too_small_for_clustering")
    if adata.obs_names.has_duplicates:
        raise ValueError("duplicate_cell_ids")
    if adata.var_names.has_duplicates:
        raise ValueError("duplicate_gene_ids")

    original_cells = pd.Index(adata.obs_names.astype(str))
    original_shape = [int(adata.n_obs), int(adata.n_vars)]
    matrix_state, state_evidence = detect_matrix_state(adata)
    warnings: list[str] = []

    if matrix_state == "raw_counts":
        detected_genes = np.asarray((adata.X > 0).sum(axis=1)).ravel()
        retained_cell_mask = detected_genes >= MIN_GENES_PER_CELL
        disposition = pd.DataFrame(
            {
                "cell_id": original_cells,
                "retained": retained_cell_mask,
                "detected_genes_before_filter": detected_genes,
            }
        )
        adata = adata[retained_cell_mask].copy()
        if adata.n_obs < 3:
            raise ValueError("fewer_than_three_cells_after_filtering")
        sc.pp.filter_genes(adata, min_cells=MIN_CELLS_PER_GENE)
        if adata.n_vars < 3:
            raise ValueError("fewer_than_three_genes_after_filtering")
        adata.layers["counts"] = adata.X.copy()
        sc.pp.normalize_total(adata, target_sum=TARGET_SUM)
        sc.pp.log1p(adata)
        normalization_action = "normalize_total_then_log1p"
    else:
        disposition = pd.DataFrame(
            {
                "cell_id": original_cells,
                "retained": np.ones(adata.n_obs, dtype=bool),
                "detected_genes_before_filter": np.asarray((adata.X > 0).sum(axis=1)).ravel(),
            }
        )
        normalization_action = "preserve_explicit_log1p"
        warnings.append("raw_counts_layer_not_created_for_explicit_log1p_input")

    n_top_genes = min(MAX_HVG, int(adata.n_vars))
    sc.pp.highly_variable_genes(adata, n_top_genes=n_top_genes, flavor="seurat")
    n_hvg = int(adata.var["highly_variable"].sum())
    n_pcs = min(MAX_PCS, int(adata.n_obs) - 1, n_hvg - 1)
    if n_pcs < 2:
        raise ValueError("insufficient_dimensions_for_pca")

    sc.pp.pca(adata, n_comps=n_pcs, mask_var="highly_variable", random_state=args.seed)
    n_neighbors = min(MAX_NEIGHBORS, int(adata.n_obs) - 1)
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs, random_state=args.seed)
    sc.tl.leiden(
        adata,
        resolution=LEIDEN_RESOLUTION,
        random_state=args.seed,
        flavor="igraph",
        n_iterations=2,
        directed=False,
        key_added="leiden",
    )
    sc.tl.umap(adata, random_state=args.seed)

    coords = np.asarray(adata.obsm["X_umap"])
    clusters = adata.obs["leiden"].astype(str)
    cell_clusters = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "leiden_cluster": clusters.to_numpy(),
            "umap_1": coords[:, 0],
            "umap_2": coords[:, 1],
        }
    )
    cluster_sizes = clusters.value_counts().sort_index(key=lambda index: index.astype(int))

    adata.uns["biodsh_preprocess"] = {
        "schema_version": "1.0",
        "seed": int(args.seed),
        "matrix_state": matrix_state,
        "normalization_action": normalization_action,
        "min_genes_per_cell": MIN_GENES_PER_CELL if matrix_state == "raw_counts" else None,
        "min_cells_per_gene": MIN_CELLS_PER_GENE if matrix_state == "raw_counts" else None,
        "target_sum": TARGET_SUM if matrix_state == "raw_counts" else None,
        "n_top_genes": n_top_genes,
        "n_pcs": n_pcs,
        "n_neighbors": n_neighbors,
        "leiden_resolution": LEIDEN_RESOLUTION,
    }

    cell_clusters.to_csv(outdir / "cell_clusters.csv", index=False)
    disposition.to_csv(outdir / "cell_disposition.csv", index=False)
    adata.write_h5ad(outdir / "processed.h5ad", compression="gzip")

    input_hash_after = sha256(input_path)
    report = {
        "schema_version": "1.0",
        "input": {
            "path": str(input_path),
            "sha256_before": input_hash_before,
            "sha256_after": input_hash_after,
            "source_unchanged": input_hash_before == input_hash_after,
        },
        "seed": int(args.seed),
        "matrix_state": matrix_state,
        "state_evidence": state_evidence,
        "normalization_action": normalization_action,
        "parameters": adata.uns["biodsh_preprocess"],
        "shape": {
            "input": original_shape,
            "processed": [int(adata.n_obs), int(adata.n_vars)],
            "removed_cells": int(original_shape[0] - adata.n_obs),
            "removed_genes": int(original_shape[1] - adata.n_vars),
        },
        "features": {
            "highly_variable_genes": n_hvg,
            "pca_components": int(adata.obsm["X_pca"].shape[1]),
            "umap_dimensions": int(coords.shape[1]),
        },
        "clustering": {
            "method": "leiden",
            "n_clusters": int(clusters.nunique()),
            "cluster_sizes": {str(key): int(value) for key, value in cluster_sizes.items()},
            "biological_labels_assigned": False,
        },
        "versions": package_versions(),
        "warnings": warnings,
    }
    (outdir / "preprocessing_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "matrix_state": matrix_state,
                "processed_shape": report["shape"]["processed"],
                "n_clusters": report["clustering"]["n_clusters"],
            }
        )
    )


if __name__ == "__main__":
    main()
