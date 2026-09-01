---
name: scrna-cellstate-annotation
description: Assign evidence-backed broad immune cell classes and T-cell states to clustered AnnData data without using clinical outcome labels.
---

# scRNA-seq cell-state annotation

Use this skill on a normalized AnnData `.h5ad` input that already contains `obs["leiden"]` clusters.

## Scientific contract

- Treat the source file as read-only and verify its SHA-256 before and after execution.
- Use expression, gene identifiers, and Leiden clusters only. Never use response, therapy, timepoint, patient, survival, or other clinical outcome metadata to assign labels.
- Resolve duplicate gene symbols by selecting the feature with the highest mean expression and report that decision.
- Score fixed broad immune and T-cell-state marker programs after per-gene standardization across cells.
- Assign labels at cluster level only when at least two program markers are present, the top score is non-negative, and its margin over the runner-up reaches the declared threshold.
- Emit `unknown` when evidence is insufficient. Do not turn marker-program labels into reference truth, clinical diagnosis, or treatment-response claims.
- Apply T-cell-state labels only to clusters assigned as `T_cell`; use `not_applicable` for other broad classes.

## Outputs

- `annotated.h5ad`: input data plus cluster-level broad and T-cell-state annotations.
- `cell_annotations.csv`: cell ID, Leiden cluster, broad class, and T-cell state only; clinical fields are excluded.
- `cluster_annotation_evidence.csv`: cluster size, every program score, selected labels, runner-up labels, and margins.
- `annotation_report.json`: marker coverage, duplicate resolution, thresholds, label counts, leakage guard, versions, and claim boundary.
