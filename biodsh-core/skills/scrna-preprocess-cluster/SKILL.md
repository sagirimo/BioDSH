---
name: scrna-preprocess-cluster
description: Preprocess and cluster an AnnData h5ad dataset with state-aware normalization, deterministic Scanpy settings, and machine-readable scientific provenance.
---

# scRNA-seq preprocessing and clustering

Use this skill after input inspection when a real AnnData `.h5ad` dataset must be normalized, reduced, and clustered.

## Scientific contract

- Treat the source file as read-only and record its SHA-256 before and after execution.
- Accept non-negative raw count matrices, or matrices explicitly marked as log1p-transformed in `adata.uns["log1p"]`.
- Refuse ambiguous continuous matrices rather than guessing whether TPM, normalized values, or log values need another transformation.
- For raw counts, filter cells with fewer than 200 detected genes and genes detected in fewer than 3 cells, retain filtered counts in `layers["counts"]`, normalize to 10,000 counts per cell, and apply `log1p`.
- Select up to 2,000 highly variable genes, then run PCA, a neighbor graph, Leiden clustering, and UMAP with the supplied seed.
- Preserve retained cell order. Never overwrite the input or claim that clusters are biological cell types.
- Record every selected branch, threshold, package version, cell disposition, and cluster size in machine-readable artifacts.

## Outputs

- `processed.h5ad`: normalized data, retained counts, HVG flags, PCA, neighbor graph, Leiden clusters, and UMAP.
- `preprocessing_report.json`: input identity, detected state, parameters, filtering, dimensions, cluster sizes, warnings, and source-integrity evidence.
- `cell_clusters.csv`: one row per retained cell in input order with Leiden cluster and UMAP coordinates.
- `cell_disposition.csv`: one row per original cell indicating whether it passed the explicit cell filter.
