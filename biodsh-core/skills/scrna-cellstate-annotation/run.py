"""Outcome-blind marker-program annotation of clustered scRNA-seq data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


BROAD_MARGIN = 0.15
STATE_MARGIN = 0.10
MIN_MARKERS = 2
CLINICAL_TOKENS = ("response", "therapy", "patient", "survival", "outcome", "timepoint")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version(name: str) -> str:
    return importlib.metadata.version(name)


def select_marker_features(adata: ad.AnnData, requested: list[str]) -> tuple[dict[str, int], dict]:
    symbols = (
        adata.var["source_gene_symbol"].astype(str).to_numpy()
        if "source_gene_symbol" in adata.var
        else adata.var_names.astype(str).to_numpy()
    )
    symbol_map: dict[str, list[int]] = {}
    for index, symbol in enumerate(symbols):
        symbol_map.setdefault(symbol.upper(), []).append(index)

    selected: dict[str, int] = {}
    evidence = {}
    for marker in requested:
        candidates = symbol_map.get(marker.upper(), [])
        if not candidates:
            evidence[marker] = {"status": "missing", "candidate_features": 0}
            continue
        subset = adata.X[:, candidates]
        means = np.asarray(subset.mean(axis=0)).ravel()
        chosen_offset = int(np.argmax(means))
        chosen = candidates[chosen_offset]
        selected[marker] = chosen
        evidence[marker] = {
            "status": "selected",
            "candidate_features": len(candidates),
            "selected_feature": str(adata.var_names[chosen]),
            "selected_mean_expression": float(means[chosen_offset]),
        }
    return selected, evidence


def standardized_marker_frame(adata: ad.AnnData, selected: dict[str, int]) -> tuple[pd.DataFrame, list[str]]:
    markers = list(selected)
    matrix = adata.X[:, [selected[marker] for marker in markers]]
    values = matrix.toarray() if sparse.issparse(matrix) else np.asarray(matrix)
    values = values.astype(np.float64, copy=False)
    means = values.mean(axis=0)
    standard_deviations = values.std(axis=0)
    usable = standard_deviations > 1e-12
    usable_markers = [marker for marker, keep in zip(markers, usable) if keep]
    standardized = (values[:, usable] - means[usable]) / standard_deviations[usable]
    return pd.DataFrame(standardized, index=adata.obs_names, columns=usable_markers), usable_markers


def module_scores(marker_z: pd.DataFrame, programs: dict[str, list[str]]) -> tuple[pd.DataFrame, dict]:
    scores = {}
    coverage = {}
    for name, markers in programs.items():
        present = [marker for marker in markers if marker in marker_z.columns]
        coverage[name] = {"requested": markers, "present": present, "present_count": len(present)}
        scores[name] = marker_z[present].mean(axis=1) if present else np.nan
    return pd.DataFrame(scores, index=marker_z.index), coverage


def choose_label(row: pd.Series, coverage: dict, margin_threshold: float) -> dict:
    eligible = {
        name: float(row[name])
        for name, item in coverage.items()
        if item["present_count"] >= MIN_MARKERS and np.isfinite(row[name])
    }
    if not eligible:
        return {"label": "unknown", "runner_up": None, "top_score": None, "margin": None}
    ranked = sorted(eligible.items(), key=lambda item: (-item[1], item[0]))
    top_label, top_score = ranked[0]
    runner_label, runner_score = ranked[1] if len(ranked) > 1 else (None, float("-inf"))
    margin = top_score - runner_score
    label = top_label if top_score >= 0.0 and margin >= margin_threshold else "unknown"
    return {
        "label": label,
        "runner_up": runner_label,
        "top_score": top_score,
        "margin": margin if np.isfinite(margin) else None,
    }


def cluster_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    source_hash_before = sha256(input_path)
    adata = ad.read_h5ad(input_path)
    if "leiden" not in adata.obs:
        raise ValueError("leiden_clusters_required")
    if adata.obs_names.has_duplicates or adata.var_names.has_duplicates:
        raise ValueError("duplicate_identifiers_not_supported")
    values = adata.X.data if sparse.issparse(adata.X) else np.asarray(adata.X).ravel()
    if values.size == 0 or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("invalid_expression_matrix")

    marker_path = Path(__file__).with_name("marker_programs.json")
    marker_spec = json.loads(marker_path.read_text(encoding="utf-8"))
    all_markers = sorted(
        {marker for section in ("broad", "t_state") for markers in marker_spec[section].values() for marker in markers}
    )
    selected, marker_evidence = select_marker_features(adata, all_markers)
    marker_z, usable_markers = standardized_marker_frame(adata, selected)
    broad_scores, broad_coverage = module_scores(marker_z, marker_spec["broad"])
    state_scores, state_coverage = module_scores(marker_z, marker_spec["t_state"])

    clusters = adata.obs["leiden"].astype(str)
    broad_cluster = broad_scores.groupby(clusters, observed=True).median()
    state_cluster = state_scores.groupby(clusters, observed=True).median()
    cluster_sizes = clusters.value_counts()
    evidence_rows = []
    assignments = {}
    for cluster in sorted(clusters.unique(), key=cluster_sort_key):
        broad_choice = choose_label(broad_cluster.loc[cluster], broad_coverage, BROAD_MARGIN)
        if broad_choice["label"] == "T_cell":
            state_choice = choose_label(state_cluster.loc[cluster], state_coverage, STATE_MARGIN)
        elif broad_choice["label"] == "unknown":
            state_choice = {"label": "unknown", "runner_up": None, "top_score": None, "margin": None}
        else:
            state_choice = {"label": "not_applicable", "runner_up": None, "top_score": None, "margin": None}
        assignments[cluster] = (broad_choice["label"], state_choice["label"])
        row = {
            "leiden_cluster": cluster,
            "n_cells": int(cluster_sizes[cluster]),
            "broad_label": broad_choice["label"],
            "broad_runner_up": broad_choice["runner_up"],
            "broad_top_score": broad_choice["top_score"],
            "broad_margin": broad_choice["margin"],
            "t_state": state_choice["label"],
            "t_state_runner_up": state_choice["runner_up"],
            "t_state_top_score": state_choice["top_score"],
            "t_state_margin": state_choice["margin"],
        }
        row.update({f"broad_{name}_score": float(broad_cluster.loc[cluster, name]) for name in broad_cluster.columns})
        row.update({f"t_state_{name}_score": float(state_cluster.loc[cluster, name]) for name in state_cluster.columns})
        evidence_rows.append(row)

    broad_labels = clusters.map({cluster: labels[0] for cluster, labels in assignments.items()})
    state_labels = clusters.map({cluster: labels[1] for cluster, labels in assignments.items()})
    adata.obs["biodsh_broad_label"] = pd.Categorical(broad_labels)
    adata.obs["biodsh_t_state"] = pd.Categorical(state_labels)
    cell_annotations = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "leiden_cluster": clusters.to_numpy(),
            "broad_label": broad_labels.to_numpy(),
            "t_state": state_labels.to_numpy(),
        }
    )
    cluster_evidence = pd.DataFrame(evidence_rows)
    clinical_columns_ignored = sorted(
        column for column in adata.obs.columns if any(token in column.lower() for token in CLINICAL_TOKENS)
    )
    adata.uns["biodsh_annotation"] = {
        "schema_version": "1.0",
        "method": "cluster_median_of_standardized_marker_programs",
        "broad_margin": BROAD_MARGIN,
        "state_margin": STATE_MARGIN,
        "minimum_markers": MIN_MARKERS,
        "clinical_metadata_used": False,
        "biological_reference_kind": "marker_program_not_ground_truth",
    }

    cell_annotations.to_csv(outdir / "cell_annotations.csv", index=False)
    cluster_evidence.to_csv(outdir / "cluster_annotation_evidence.csv", index=False)
    adata.write_h5ad(outdir / "annotated.h5ad", compression="lzf")
    source_hash_after = sha256(input_path)
    report = {
        "schema_version": "1.0",
        "input": {
            "path": str(input_path),
            "sha256_before": source_hash_before,
            "sha256_after": source_hash_after,
            "source_unchanged": source_hash_before == source_hash_after,
        },
        "seed": int(args.seed),
        "method": adata.uns["biodsh_annotation"],
        "marker_program_sha256": sha256(marker_path),
        "marker_coverage": {"broad": broad_coverage, "t_state": state_coverage},
        "marker_feature_resolution": marker_evidence,
        "usable_marker_count": len(usable_markers),
        "clusters": int(clusters.nunique()),
        "broad_label_cells": broad_labels.value_counts().sort_index().to_dict(),
        "t_state_cells": state_labels.value_counts().sort_index().to_dict(),
        "leakage_guard": {
            "clinical_metadata_used": False,
            "clinical_columns_present_but_ignored": clinical_columns_ignored,
            "cell_annotation_columns": cell_annotations.columns.tolist(),
        },
        "versions": {name: version(name) for name in ("anndata", "numpy", "pandas", "scipy")},
        "claim_boundary": "Marker-program annotations are hypotheses, not reference truth or treatment-response evidence.",
    }
    (outdir / "annotation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "clusters": report["clusters"], "broad_label_cells": report["broad_label_cells"]}))


if __name__ == "__main__":
    main()
