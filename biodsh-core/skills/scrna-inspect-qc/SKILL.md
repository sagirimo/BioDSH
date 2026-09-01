---
name: scrna-inspect-qc
description: Inspect an input AnnData h5ad file and produce auditable single-cell RNA-seq quality-control evidence without modifying or filtering the source data.
---

# scRNA-seq inspect and QC

Use this skill before normalization, integration, clustering, annotation, or differential expression when the input is an AnnData `.h5ad` file.

## Required behavior

- Treat the input as read-only and preserve its cell and gene order.
- Report matrix shape, sparsity, annotations, layers, duplicate identifiers, non-finite or negative values, and whether values appear count-like.
- Calculate per-cell and per-gene QC metrics. Detect mitochondrial genes using both human `MT-` and mouse `mt-` prefixes.
- Do not silently filter cells, choose biological thresholds, normalize values, or claim that a dataset has passed QC.
- Distinguish measured evidence from recommendations. Missing mitochondrial genes or metadata is a warning, not proof of invalid data.
- Emit machine-readable JSON and CSV artifacts so that benchmark graders do not need to parse prose.

## Outputs

- `dataset_profile.json`: input identity, matrix characteristics, annotations, warnings, and summary quantiles.
- `cell_qc.csv`: per-cell counts, detected genes, and mitochondrial fraction when available.
- `gene_qc.csv`: per-gene counts and detected-cell frequency.
