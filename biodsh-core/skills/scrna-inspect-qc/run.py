"""Read-only scRNA-seq input inspection and QC evidence generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_and_value_summary(matrix) -> dict:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if values.size == 0:
        return {
            "stored_values": 0,
            "nonfinite_values": 0,
            "negative_values": 0,
            "integer_like_fraction": None,
            "appears_count_like": False,
        }

    finite = np.isfinite(values)
    finite_values = values[finite]
    integer_like = np.isclose(finite_values, np.rint(finite_values), atol=1e-6)
    integer_like_fraction = float(integer_like.mean()) if finite_values.size else None
    negative_values = int(np.count_nonzero(finite_values < 0))
    return {
        "stored_values": int(values.size),
        "nonfinite_values": int(np.count_nonzero(~finite)),
        "negative_values": negative_values,
        "integer_like_fraction": integer_like_fraction,
        "appears_count_like": bool(
            finite_values.size
            and negative_values == 0
            and integer_like_fraction is not None
            and integer_like_fraction >= 0.99
        ),
    }


def quantiles(series: pd.Series) -> dict:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {}
    return {
        "min": float(clean.min()),
        "q25": float(clean.quantile(0.25)),
        "median": float(clean.median()),
        "q75": float(clean.quantile(0.75)),
        "max": float(clean.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    adata = ad.read_h5ad(input_path)
    matrix_summary = finite_and_value_summary(adata.X)
    duplicate_obs = int(adata.obs_names.duplicated().sum())
    duplicate_var = int(adata.var_names.duplicated().sum())

    gene_names = pd.Index(adata.var_names.astype(str))
    mt_mask = gene_names.str.startswith("MT-") | gene_names.str.startswith("mt-")

    if sparse.issparse(adata.X):
        total_counts = np.asarray(adata.X.sum(axis=1)).ravel()
        detected_genes = np.asarray((adata.X > 0).sum(axis=1)).ravel()
        gene_counts = np.asarray(adata.X.sum(axis=0)).ravel()
        detected_cells = np.asarray((adata.X > 0).sum(axis=0)).ravel()
        mt_counts = np.asarray(adata.X[:, mt_mask].sum(axis=1)).ravel() if mt_mask.any() else None
        nonzero = int(adata.X.nnz)
    else:
        matrix = np.asarray(adata.X)
        total_counts = matrix.sum(axis=1)
        detected_genes = (matrix > 0).sum(axis=1)
        gene_counts = matrix.sum(axis=0)
        detected_cells = (matrix > 0).sum(axis=0)
        mt_counts = matrix[:, mt_mask].sum(axis=1) if mt_mask.any() else None
        nonzero = int(np.count_nonzero(matrix))

    cell_qc = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "total_counts": total_counts,
            "n_genes_by_counts": detected_genes,
        }
    )
    if mt_counts is not None:
        cell_qc["pct_counts_mt"] = np.divide(
            mt_counts * 100.0,
            total_counts,
            out=np.full(total_counts.shape, np.nan, dtype=float),
            where=total_counts != 0,
        )

    gene_qc = pd.DataFrame(
        {
            "gene_id": gene_names,
            "total_counts": gene_counts,
            "n_cells_by_counts": detected_cells,
            "is_mitochondrial": mt_mask,
        }
    )

    warnings = []
    if adata.n_obs == 0 or adata.n_vars == 0:
        warnings.append("empty_matrix")
    if duplicate_obs:
        warnings.append("duplicate_cell_ids")
    if duplicate_var:
        warnings.append("duplicate_gene_ids")
    if matrix_summary["nonfinite_values"]:
        warnings.append("nonfinite_values")
    if matrix_summary["negative_values"]:
        warnings.append("negative_values")
    if not mt_mask.any():
        warnings.append("mitochondrial_genes_not_detected")
    if len(adata.obs.columns) == 0:
        warnings.append("cell_metadata_absent")

    total_slots = int(adata.n_obs * adata.n_vars)
    profile = {
        "schema_version": "1.0",
        "input": {
            "path": str(input_path),
            "sha256": sha256(input_path),
            "format": "h5ad",
        },
        "shape": {"cells": int(adata.n_obs), "genes": int(adata.n_vars)},
        "matrix": {
            "storage": "sparse" if sparse.issparse(adata.X) else "dense",
            "dtype": str(adata.X.dtype),
            "nonzero_values": nonzero,
            "sparsity": 1.0 - (nonzero / total_slots) if total_slots else None,
            **matrix_summary,
        },
        "identifiers": {
            "duplicate_cell_ids": duplicate_obs,
            "duplicate_gene_ids": duplicate_var,
        },
        "annotations": {
            "obs_columns": [str(column) for column in adata.obs.columns],
            "var_columns": [str(column) for column in adata.var.columns],
            "layers": [str(key) for key in adata.layers.keys() if key is not None],
            "obsm": [str(key) for key in adata.obsm.keys() if key is not None],
            "uns": [str(key) for key in adata.uns.keys() if key is not None],
        },
        "qc_summary": {
            "total_counts": quantiles(cell_qc["total_counts"]),
            "n_genes_by_counts": quantiles(cell_qc["n_genes_by_counts"]),
            "pct_counts_mt": quantiles(cell_qc["pct_counts_mt"])
            if "pct_counts_mt" in cell_qc
            else {},
            "mitochondrial_gene_count": int(mt_mask.sum()),
        },
        "warnings": warnings,
        "interpretation": {
            "source_modified": False,
            "cells_filtered": 0,
            "thresholds_applied": False,
        },
    }

    cell_qc.to_csv(outdir / "cell_qc.csv", index=False)
    gene_qc.to_csv(outdir / "gene_qc.csv", index=False)
    (outdir / "dataset_profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "shape": profile["shape"], "warnings": warnings}))


if __name__ == "__main__":
    main()
