---
name: scrna-virtual-knockout
description: In-silico single-gene knockout on scRNA-seq (scTenifoldKnk-style): build a gene regulatory network, virtually knock out a gene, and rank the genes most affected by its loss.
---

# scRNA-seq virtual (in-silico) knockout

Use this skill to predict, entirely in silico, what happens to a single-cell transcriptome
when one gene is removed — no wet-lab knockout required. It reimplements the
**scTenifoldKnk** concept in Python: learn a gene regulatory network (GRN) from a wild-type
scRNA-seq sample, delete the target gene from that network, then use manifold alignment to
find which genes shift the most between the intact (WT) and knockout (KO) networks. Those
top-shifting genes are the predicted downstream effects of losing the target gene.

## When to use it

- The user asks "what would happen if we knocked out gene X?" for a single-cell dataset.
- The user wants to prioritize downstream / co-regulated genes of a transcription factor or
  regulator without doing a real perturbation.
- Hypothesis generation before a CRISPR / shRNA experiment.

Do **not** use it as a substitute for a real perturbation experiment — it is a prediction
about network topology, not measured biology (see Caveats).

## Required inputs

- `--input` : a single `.h5ad` (AnnData) file, cells × genes. Ideally a single, reasonably
  homogeneous wild-type population (one cell type / condition) — the GRN assumes one regime.
- `--gene`  : the gene symbol to knock out. It must be present in `var_names` (or its index).
  If it is missing, the script errors and lists similar names.

The analysis is **read-only** on the input `.h5ad`; it is never modified.

## How to run it

The analysis-environment python is on `PATH` inside this skill's runtime (the BioDSH bioenv),
so just call:

```
python run.py --input <path/to/sample.h5ad> --gene <GENE> --outdir <output_dir>
```

Useful options:

- `--n-hvg N`  : cap the network to the top N highly variable genes (default 2000). The
  target gene is always forced in. **Heavy compute scales with the square of the gene count**
  (an N×N network plus per-gene regression and eigendecomposition), so keep N modest
  (1000–3000) for interactive runs. Lower it for large or slow datasets.
- `--seed S`   : random seed for reproducibility (default 0).

Example:

```
python run.py --input data/pbmc_wt.h5ad --gene GATA1 --outdir results/ko_gata1 --n-hvg 2000
```

## How to read the outputs

Written into `--outdir`:

- `virtual_ko_ranked.csv` — every gene in the network ranked by how much the knockout
  perturbs it. Columns: `gene`, `distance` (WT↔KO aligned-coordinate distance; larger = more
  affected), `pvalue`, `FDR` (Benjamini–Hochberg), `rank`. The top of this table is the
  predicted "regulon" / downstream response of the target gene.
- `virtual_ko_top_genes.png` — barplot of the ~20 most affected genes.
- `virtual_ko_summary.json` — target gene, `n_cells`, `n_genes` used, number of genes
  significant at FDR < 0.05, the top-10 gene list, and the run parameters.

A short human-readable summary is also printed to stdout.

Interpretation: genes with the largest `distance` and smallest `FDR` are the ones whose
regulatory context collapses most when the target is removed — i.e. the predicted knockout
signature. Confirm they are biologically plausible partners of the target before acting.

## Method (scTenifoldKnk-style)

1. Load and (if the matrix looks like raw counts) library-size normalize + `log1p`; select the
   top-N HVGs, forcing the target gene in.
2. Build the WT GRN with **pcNet** (principal-component regression): each gene is regressed on
   the top principal components of the other genes; the coefficients are its incoming edges.
   The genes×genes adjacency is symmetrized and scaled to [-1, 1] by max absolute value —
   as in scTenifoldNet.
3. Knock out: copy the WT network and zero the target gene's row **and** column.
4. Compare WT vs KO by **manifold alignment** (Laplacian-eigenmap embeddings aligned with
   orthogonal Procrustes); per-gene distance = Euclidean distance between its WT and KO
   aligned coordinates.
5. Rank by distance; assign significance via a Box–Cox transform of the distances followed by
   a normal-tail p-value and BH-FDR (the scTenifoldKnk significance scheme).

## Caveats

- This is a **Python reimplementation of the scTenifoldKnk concept**. The canonical reference
  methods are **scTenifoldKnk** and **scTenifoldNet** (Osorio et al.); if the user has R, the
  original R package **scTenifoldKnk** is the authoritative implementation and should be
  preferred for publication-grade results.
- Predictions are only as good as the GRN, which needs enough cells and a single, coherent
  cell state. Mixed cell types, batch effects, or very few cells degrade results.
- Results are network/topology predictions, not measured effects — treat them as hypotheses.
