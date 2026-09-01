"""Patient-aware exploratory treatment-response association for annotated scRNA-seq data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import math
import re
from pathlib import Path

import anndata as ad
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED_COLUMNS = (
    "patient_id",
    "specimen_id",
    "response",
    "timepoint",
    "therapy",
    "biodsh_broad_label",
    "biodsh_t_state",
)
RESPONSE_LABELS = ("Non-responder", "Responder")
ANALYSIS_SETS = {
    "primary_all_specimens": {"timepoint": None, "stable_therapy": None},
    "sensitivity_pre_only": {"timepoint": "Pre", "stable_therapy": None},
    "sensitivity_post_only": {"timepoint": "Post", "stable_therapy": None},
    "sensitivity_stable_anti_pd1": {"timepoint": None, "stable_therapy": "anti-PD1"},
}
DEFAULT_PERMUTATIONS = 100_000
DEFAULT_BOOTSTRAPS = 10_000
MAX_EXACT_PERMUTATIONS = 250_000
MIN_TOTAL_CELLS = 100
MIN_T_CELLS = 50
BROAD_PALETTE = {
    "B_cell": "#1f77b4",
    "NK_cell": "#ff7f0e",
    "T_cell": "#2ca02c",
    "myeloid": "#d62728",
    "plasma_cell": "#9467bd",
    "dendritic": "#8c564b",
    "unknown": "#8a8a8a",
    "not_applicable": "#d9d9d9",
}
T_STATE_PALETTE = {
    "activation": "#1f77b4",
    "exhaustion": "#ff7f0e",
    "naive_memory": "#2ca02c",
    "cytotoxic": "#d62728",
    "regulatory": "#9467bd",
    "cycling": "#8c564b",
    "interferon": "#e377c2",
    "unknown": "#8a8a8a",
    "not_applicable": "#d9d9d9",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version(name: str) -> str:
    return importlib.metadata.version(name)


def natural_key(value: str) -> tuple:
    return tuple(int(item) if item.isdigit() else item.lower() for item in re.split(r"(\d+)", value))


def ordered_categories(values: pd.Series, preferred: tuple[str, ...] = ()) -> list[str]:
    observed = {str(value) for value in values.dropna().astype(str)}
    ordered = [value for value in preferred if value in observed]
    ordered.extend(sorted(observed - set(ordered) - {"unknown", "not_applicable"}))
    ordered.extend(value for value in ("unknown", "not_applicable") if value in observed)
    return ordered


def join_unique(values: pd.Series) -> str:
    return "|".join(sorted({str(value) for value in values}, key=natural_key))


def validate_input(adata: ad.AnnData) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in adata.obs]
    if missing:
        raise ValueError(f"required_obs_columns_missing:{','.join(missing)}")
    if adata.obs_names.has_duplicates:
        raise ValueError("duplicate_cell_identifiers_not_supported")
    if adata.obs[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("missing_required_obs_values")
    observed_responses = set(adata.obs["response"].astype(str))
    if not observed_responses <= set(RESPONSE_LABELS):
        raise ValueError(f"unsupported_response_labels:{sorted(observed_responses)}")
    if "X_umap" not in adata.obsm or adata.obsm["X_umap"].shape != (adata.n_obs, 2):
        raise ValueError("two_dimensional_umap_required")
    annotation = adata.uns.get("biodsh_annotation", {})
    if annotation.get("clinical_metadata_used") is not False:
        raise ValueError("outcome_blind_upstream_annotation_required")


def derive_specimen_table(obs: pd.DataFrame) -> pd.DataFrame:
    records = []
    for specimen_id, frame in obs.groupby("specimen_id", observed=True, sort=False):
        record = {"specimen_id": str(specimen_id), "n_cells": int(len(frame))}
        for column in ("patient_id", "response", "timepoint", "therapy"):
            values = sorted(set(frame[column].astype(str)))
            if len(values) != 1:
                raise ValueError(f"inconsistent_{column}_within_specimen:{specimen_id}")
            record[column] = values[0]
        records.append(record)
    return pd.DataFrame(records).sort_values("specimen_id", key=lambda x: x.map(natural_key)).reset_index(drop=True)


def derive_patient_summary(specimens: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for patient_id, frame in specimens.groupby("patient_id", sort=False):
        responses = sorted(set(frame["response"].astype(str)))
        consistent = len(responses) == 1
        rows.append(
            {
                "patient_id": str(patient_id),
                "patient_response": responses[0] if consistent else "ambiguous",
                "response_status": "consistent" if consistent else "ambiguous_longitudinal",
                "responses": "|".join(responses),
                "n_specimens": int(len(frame)),
                "n_cells": int(frame["n_cells"].sum()),
                "specimens": join_unique(frame["specimen_id"]),
                "timepoints": join_unique(frame["timepoint"]),
                "therapies": join_unique(frame["therapy"]),
            }
        )
    return pd.DataFrame(rows).sort_values("patient_id", key=lambda x: x.map(natural_key)).reset_index(drop=True)


def validate_patient_response_metadata(obs: pd.DataFrame, patients: pd.DataFrame) -> None:
    if "patient_response" not in obs:
        return
    expected = patients.set_index("patient_id")["patient_response"].to_dict()
    observed = obs["patient_response"].astype(str)
    derived = obs["patient_id"].astype(str).map(expected)
    if not observed.equals(derived.astype(str)):
        raise ValueError("patient_response_metadata_disagrees_with_specimen_records")


def aggregate_specimen_composition(obs: pd.DataFrame, specimen_meta: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    specimen_ids = specimen_meta["specimen_id"].astype(str).tolist()
    specimen_series = obs["specimen_id"].astype(str)
    broad_series = obs["biodsh_broad_label"].astype(str)
    broad_categories = ordered_categories(
        broad_series,
        ("T_cell", "NK_cell", "B_cell", "plasma_cell", "myeloid", "dendritic"),
    )
    broad_counts = pd.crosstab(specimen_series, broad_series).reindex(
        index=specimen_ids, columns=broad_categories, fill_value=0
    )
    broad_props = broad_counts.div(broad_counts.sum(axis=1), axis=0)
    broad_props.columns = [f"broad__{column}" for column in broad_props.columns]

    t_mask = broad_series == "T_cell"
    t_states = obs.loc[t_mask, "biodsh_t_state"].astype(str)
    if "not_applicable" in set(t_states):
        raise ValueError("t_cells_cannot_have_not_applicable_state")
    t_categories = ordered_categories(
        t_states,
        ("naive_memory", "cytotoxic", "exhaustion", "regulatory", "cycling", "interferon", "activation"),
    )
    t_counts = pd.crosstab(specimen_series[t_mask], t_states).reindex(
        index=specimen_ids, columns=t_categories, fill_value=0
    )
    t_denominator = t_counts.sum(axis=1)
    t_props = t_counts.div(t_denominator.replace(0, np.nan), axis=0)
    t_props.columns = [f"tstate__{column}" for column in t_props.columns]

    table = specimen_meta.set_index("specimen_id").copy()
    table["n_t_cells"] = t_denominator.astype(int)
    table["broad_eligible"] = table["n_cells"] >= MIN_TOTAL_CELLS
    table["tstate_eligible"] = table["n_t_cells"] >= MIN_T_CELLS
    table = table.join(broad_props).join(t_props).reset_index()
    broad_columns = broad_props.columns.tolist()
    t_columns = t_props.columns.tolist()
    return table, broad_columns, t_columns


def aggregate_patient_timepoints(
    specimens: pd.DataFrame,
    broad_columns: list[str],
    t_columns: list[str],
) -> pd.DataFrame:
    rows = []
    for (patient_id, timepoint), frame in specimens.groupby(["patient_id", "timepoint"], sort=False):
        response_values = sorted(set(frame["response"].astype(str)))
        broad_frame = frame[frame["broad_eligible"]]
        t_frame = frame[frame["tstate_eligible"]]
        row = {
            "patient_id": str(patient_id),
            "timepoint": str(timepoint),
            "response": response_values[0] if len(response_values) == 1 else "ambiguous",
            "response_status": "consistent" if len(response_values) == 1 else "ambiguous_within_timepoint",
            "n_specimens": int(len(frame)),
            "n_specimens_broad": int(len(broad_frame)),
            "n_specimens_tstate": int(len(t_frame)),
            "n_cells": int(frame["n_cells"].sum()),
            "n_t_cells": int(frame["n_t_cells"].sum()),
            "specimens": join_unique(frame["specimen_id"]),
            "therapies": join_unique(frame["therapy"]),
        }
        row.update(
            {
                column: (float(broad_frame[column].mean()) if len(broad_frame) else np.nan)
                for column in broad_columns
            }
        )
        row.update(
            {column: (float(t_frame[column].mean()) if len(t_frame) else np.nan) for column in t_columns}
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["patient_id", "timepoint"], key=lambda x: x.map(natural_key) if x.name == "patient_id" else x
    ).reset_index(drop=True)


def build_analysis_patient_composition(
    patient_timepoints: pd.DataFrame,
    patients: pd.DataFrame,
    broad_columns: list[str],
    t_columns: list[str],
) -> pd.DataFrame:
    consistent_ids = set(patients.loc[patients["response_status"] == "consistent", "patient_id"])
    stable_therapy = patients.set_index("patient_id")["therapies"].to_dict()
    feature_columns = broad_columns + t_columns
    rows = []
    for analysis_set, specification in ANALYSIS_SETS.items():
        selected = patient_timepoints[patient_timepoints["patient_id"].isin(consistent_ids)].copy()
        if specification["timepoint"] is not None:
            selected = selected[selected["timepoint"] == specification["timepoint"]]
        if specification["stable_therapy"] is not None:
            eligible_ids = {
                patient_id
                for patient_id, therapies in stable_therapy.items()
                if therapies == specification["stable_therapy"]
            }
            selected = selected[selected["patient_id"].isin(eligible_ids)]
        for patient_id, frame in selected.groupby("patient_id", sort=False):
            response_values = sorted(set(frame["response"].astype(str)))
            if len(response_values) != 1:
                raise ValueError(f"ambiguous_patient_entered_analysis:{patient_id}")
            row = {
                "analysis_set": analysis_set,
                "patient_id": str(patient_id),
                "response": response_values[0],
                "n_timepoints_aggregated": int(len(frame)),
                "n_specimens_aggregated": int(frame["n_specimens"].sum()),
                "n_specimens_broad": int(frame["n_specimens_broad"].sum()),
                "n_specimens_tstate": int(frame["n_specimens_tstate"].sum()),
                "n_cells": int(frame["n_cells"].sum()),
                "n_t_cells": int(frame["n_t_cells"].sum()),
                "timepoints": join_unique(frame["timepoint"]),
                "therapies": join_unique(frame["therapies"]),
            }
            row.update({column: float(frame[column].mean()) for column in feature_columns})
            rows.append(row)
    result = pd.DataFrame(rows)
    return result.sort_values(
        ["analysis_set", "patient_id"], key=lambda x: x.map(natural_key) if x.name == "patient_id" else x
    ).reset_index(drop=True)


def build_confounding_counts(patients: pd.DataFrame) -> pd.DataFrame:
    primary = patients[patients["analysis_set"] == "primary_all_specimens"].copy()
    rows = []
    for dimension, column in (("therapy_profile", "therapies"), ("timepoint_profile", "timepoints")):
        counts = primary.groupby([column, "response"], observed=True).size()
        for (level, response), count in counts.items():
            rows.append(
                {
                    "dimension": dimension,
                    "level": str(level),
                    "response": str(response),
                    "n_patients": int(count),
                }
            )
    return pd.DataFrame(rows).sort_values(["dimension", "level", "response"]).reset_index(drop=True)


def stable_seed(base_seed: int, *parts: str) -> int:
    payload = "|".join([str(base_seed), *parts]).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "little")


def mean_difference(values: np.ndarray, labels: np.ndarray) -> float:
    responders = labels == "Responder"
    return float(values[responders].mean() - values[~responders].mean())


def permutation_p_value(
    values: np.ndarray,
    labels: np.ndarray,
    permutations: int,
    seed: int,
    max_exact: int = MAX_EXACT_PERMUTATIONS,
) -> tuple[float, str, int]:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=str)
    observed = mean_difference(values, labels)
    responder_count = int(np.sum(labels == "Responder"))
    total_unique = math.comb(len(values), responder_count)
    extreme = 0
    if total_unique <= max_exact:
        total_sum = float(values.sum())
        non_responder_count = len(values) - responder_count
        for responder_positions in itertools.combinations(range(len(values)), responder_count):
            responder_sum = float(values[list(responder_positions)].sum())
            statistic = responder_sum / responder_count - (total_sum - responder_sum) / non_responder_count
            extreme += int(abs(statistic) >= abs(observed) - 1e-15)
        return float(extreme / total_unique), "exact", int(total_unique)

    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        permuted_positions = rng.permutation(len(values))
        permuted = np.full(len(values), "Non-responder", dtype=object)
        permuted[permuted_positions[:responder_count]] = "Responder"
        statistic = mean_difference(values, permuted.astype(str))
        extreme += int(abs(statistic) >= abs(observed) - 1e-15)
    return float((extreme + 1) / (permutations + 1)), "monte_carlo", int(permutations)


def bootstrap_difference_ci(
    values: np.ndarray,
    labels: np.ndarray,
    bootstraps: int,
    seed: int,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=str)
    responder = values[labels == "Responder"]
    non_responder = values[labels == "Non-responder"]
    rng = np.random.default_rng(seed)
    differences = np.empty(bootstraps, dtype=float)
    for index in range(bootstraps):
        resampled_r = responder[rng.integers(0, len(responder), len(responder))]
        resampled_nr = non_responder[rng.integers(0, len(non_responder), len(non_responder))]
        differences[index] = resampled_r.mean() - resampled_nr.mean()
    low, high = np.quantile(differences, [0.025, 0.975])
    return float(low), float(high)


def cliffs_delta(values: np.ndarray, labels: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=str)
    responder = values[labels == "Responder"]
    non_responder = values[labels == "Non-responder"]
    comparisons = np.sign(responder[:, None] - non_responder[None, :])
    return float(comparisons.mean())


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    ranked = values[order] * len(values) / np.arange(1, len(values) + 1)
    adjusted_ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adjusted = np.empty_like(adjusted_ranked)
    adjusted[order] = np.minimum(adjusted_ranked, 1.0)
    return adjusted


def build_associations(
    patients: pd.DataFrame,
    broad_columns: list[str],
    t_columns: list[str],
    permutations: int,
    bootstraps: int,
    seed: int,
) -> pd.DataFrame:
    rows = []
    for analysis_set in ANALYSIS_SETS:
        analysis = patients[patients["analysis_set"] == analysis_set]
        analysis_rows = []
        for family, columns in (("broad_all_cells", broad_columns), ("t_state_within_t", t_columns)):
            for column in columns:
                available = analysis[["patient_id", "response", column]].dropna()
                values = available[column].to_numpy(dtype=float)
                labels = available["response"].to_numpy(dtype=str)
                n_responder = int(np.sum(labels == "Responder"))
                n_non_responder = int(np.sum(labels == "Non-responder"))
                feature = column.split("__", 1)[1]
                estimable = n_responder >= 2 and n_non_responder >= 2
                tested = estimable and feature != "unknown" and float(np.ptp(values)) > 1e-12
                if estimable:
                    effect = mean_difference(values, labels)
                    ci_low, ci_high = bootstrap_difference_ci(
                        values,
                        labels,
                        bootstraps,
                        stable_seed(seed, analysis_set, family, column, "bootstrap"),
                    )
                    delta = cliffs_delta(values, labels)
                else:
                    effect = ci_low = ci_high = delta = np.nan
                if tested:
                    p_value, permutation_mode, permutations_evaluated = permutation_p_value(
                        values,
                        labels,
                        permutations,
                        stable_seed(seed, analysis_set, family, column, "permutation"),
                    )
                else:
                    p_value = np.nan
                    permutation_mode = "not_tested"
                    permutations_evaluated = 0
                analysis_rows.append(
                    {
                        "analysis_set": analysis_set,
                        "feature_family": family,
                        "feature": feature,
                        "feature_column": column,
                        "inferential_unit": "patient",
                        "n_responder": n_responder,
                        "n_non_responder": n_non_responder,
                        "mean_responder": float(values[labels == "Responder"].mean()) if n_responder else np.nan,
                        "mean_non_responder": (
                            float(values[labels == "Non-responder"].mean()) if n_non_responder else np.nan
                        ),
                        "mean_difference_pp": effect * 100.0,
                        "ci95_low_pp": ci_low * 100.0,
                        "ci95_high_pp": ci_high * 100.0,
                        "cliffs_delta": delta,
                        "permutation_p_value": p_value,
                        "fdr_bh_analysis_set": np.nan,
                        "permutation_mode": permutation_mode,
                        "permutations_requested": permutations,
                        "permutations_evaluated": permutations_evaluated,
                        "bootstraps": bootstraps,
                        "tested": tested,
                    }
                )
        tested_indices = [index for index, row in enumerate(analysis_rows) if row["tested"]]
        if tested_indices:
            adjusted = benjamini_hochberg(
                np.array([analysis_rows[index]["permutation_p_value"] for index in tested_indices])
            )
            for index, q_value in zip(tested_indices, adjusted):
                analysis_rows[index]["fdr_bh_analysis_set"] = float(q_value)
        rows.extend(analysis_rows)
    return pd.DataFrame(rows)


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "BioDSH"})
    plt.close(fig)


def plot_umap(adata: ad.AnnData, column: str, title: str, path: Path, only_t_cells: bool = False) -> None:
    labels = adata.obs[column].astype(str)
    mask = np.ones(adata.n_obs, dtype=bool)
    if only_t_cells:
        mask = adata.obs["biodsh_broad_label"].astype(str).to_numpy() == "T_cell"
    coordinates = np.asarray(adata.obsm["X_umap"])[mask]
    shown_labels = labels.to_numpy()[mask]
    categories = ordered_categories(pd.Series(shown_labels))
    cmap = plt.get_cmap("tab10")
    palette = BROAD_PALETTE if column == "biodsh_broad_label" else T_STATE_PALETTE
    fig, ax = plt.subplots(figsize=(8.4, 6.4))
    total = len(shown_labels)
    for index, category in enumerate(categories):
        selected = shown_labels == category
        color = palette.get(category, cmap(index % 10))
        ax.scatter(
            coordinates[selected, 0],
            coordinates[selected, 1],
            s=4,
            alpha=0.58,
            linewidths=0,
            rasterized=True,
            color=color,
            label=f"{category}  n={int(selected.sum()):,} ({selected.mean() * 100:.1f}%)",
        )
    ax.set(title=title, xlabel="UMAP 1", ylabel="UMAP 2")
    ax.legend(frameon=False, markerscale=3, bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.text(
        0,
        -0.14,
        "Outcome-blind marker-program labels; hypotheses, not reference truth.",
        transform=ax.transAxes,
        fontsize=8,
    )
    save_figure(fig, path)


def plot_patient_composition(patients: pd.DataFrame, broad_columns: list[str], path: Path) -> None:
    subsets = [
        ("primary_all_specimens", "All timepoints: equal-weight patient mean"),
        ("sensitivity_pre_only", "Pre-treatment specimens only"),
    ]
    prepared = []
    for analysis_set, title in subsets:
        frame = patients[patients["analysis_set"] == analysis_set].copy()
        frame["response_order"] = frame["response"].map({"Non-responder": 0, "Responder": 1})
        frame = frame.sort_values(
            ["response_order", "patient_id"],
            key=lambda x: x.map(natural_key) if x.name == "patient_id" else x,
        )
        prepared.append((frame, title))
    fig_height = max(8.0, max(len(frame) for frame, _ in prepared) * 0.31)
    fig, axes = plt.subplots(1, 2, figsize=(18.0, fig_height))
    cmap = plt.get_cmap("tab10")
    for panel_index, ((frame, title), ax) in enumerate(zip(prepared, axes)):
        left = np.zeros(len(frame))
        for index, column in enumerate(broad_columns):
            values = frame[column].to_numpy(dtype=float)
            category = column.split("__", 1)[1]
            ax.barh(
                np.arange(len(frame)),
                values,
                left=left,
                label=category,
                color=BROAD_PALETTE.get(category, cmap(index % 10)),
            )
            left += values
        labels = [
            f"{patient} {'R' if response == 'Responder' else 'NR'} | {n_timepoints}tp/{n_specimens}sp"
            for patient, response, n_timepoints, n_specimens in zip(
                frame["patient_id"],
                frame["response"],
                frame["n_timepoints_aggregated"],
                frame["n_specimens_aggregated"],
            )
        ]
        ax.set_yticks(np.arange(len(frame)), labels)
        ax.invert_yaxis()
        ax.set_xlim(0, 1)
        ax.set_xlabel("Patient-level cell proportion")
        ax.set_title(f"{title} (n={len(frame)})")
        if panel_index == 1:
            ax.legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.suptitle("Broad immune-cell composition by patient")
    fig.text(
        0.5,
        0.01,
        "R, responder; NR, non-responder; tp, timepoints; sp, specimens. Timepoints are equally weighted; descriptive only.",
        ha="center",
        fontsize=8,
    )
    fig.subplots_adjust(left=0.12, right=0.88, bottom=0.08, top=0.91, wspace=0.28)
    save_figure(fig, path)


def plot_cohort_flow(patient_summary: pd.DataFrame, specimens: pd.DataFrame, analysis_patients: pd.DataFrame, path: Path) -> None:
    consistent = patient_summary[patient_summary["response_status"] == "consistent"]
    ambiguous = patient_summary[patient_summary["response_status"] != "consistent"]
    counts_by_set = {
        analysis_set: analysis_patients.loc[
            analysis_patients["analysis_set"] == analysis_set, "response"
        ].value_counts()
        for analysis_set in ANALYSIS_SETS
    }
    primary_counts = counts_by_set["primary_all_specimens"]
    pre_counts = counts_by_set["sensitivity_pre_only"]
    post_counts = counts_by_set["sensitivity_post_only"]
    anti_pd1_counts = counts_by_set["sensitivity_stable_anti_pd1"]
    ambiguous_ids = ", ".join(ambiguous["patient_id"].tolist())
    fig, ax = plt.subplots(figsize=(11.5, 5.5))
    ax.axis("off")
    boxes = [
        (0.03, 0.55, f"Public cohort\n{len(patient_summary)} patients\n{len(specimens)} specimens"),
        (
            0.37,
            0.79,
            f"Primary association\n{len(consistent)} consistent patients\n"
            f"{int(primary_counts.get('Non-responder', 0))} NR / {int(primary_counts.get('Responder', 0))} R",
        ),
        (0.37, 0.18, f"Excluded from inference\n{len(ambiguous)} ambiguous patients\n{ambiguous_ids}"),
        (
            0.72,
            0.70,
            f"Pre-only sensitivity\n{int(pre_counts.sum())} patients\n"
            f"{int(pre_counts.get('Non-responder', 0))} NR / {int(pre_counts.get('Responder', 0))} R",
        ),
        (
            0.72,
            0.47,
            f"Post-only sensitivity\n{int(post_counts.sum())} patients\n"
            f"{int(post_counts.get('Non-responder', 0))} NR / {int(post_counts.get('Responder', 0))} R",
        ),
        (
            0.72,
            0.15,
            f"Stable anti-PD1 sensitivity\n{int(anti_pd1_counts.sum())} patients\n"
            f"{int(anti_pd1_counts.get('Non-responder', 0))} NR / "
            f"{int(anti_pd1_counts.get('Responder', 0))} R",
        ),
    ]
    for x, y, label in boxes:
        ax.text(
            x,
            y,
            label,
            transform=ax.transAxes,
            ha="left",
            va="center",
            bbox={"boxstyle": "round,pad=0.6", "facecolor": "#f0f0f0", "edgecolor": "#777777"},
        )
    ax.text(
        0.72,
        0.94,
        "Overlapping sensitivity subsets\n(not mutually exclusive)",
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=9,
        fontweight="bold",
    )
    cohort_arrows = [
        ((0.24, 0.58), (0.36, 0.72)),
        ((0.24, 0.52), (0.36, 0.30)),
    ]
    sensitivity_arrows = [
        ((0.60, 0.73), (0.71, 0.79)),
        ((0.60, 0.69), (0.71, 0.47)),
        ((0.60, 0.65), (0.71, 0.15)),
    ]
    for start, end in cohort_arrows:
        ax.annotate("", xy=end, xytext=start, xycoords="axes fraction", arrowprops={"arrowstyle": "->", "lw": 1.5})
    for start, end in sensitivity_arrows:
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            xycoords="axes fraction",
            arrowprops={"arrowstyle": "->", "lw": 1.5, "linestyle": "--"},
        )
    ax.set_title("Patient-level cohort flow and longitudinal response safeguard")
    save_figure(fig, path)


def plot_recorded_response_associations(associations: pd.DataFrame, path: Path) -> None:
    shown = associations[np.isfinite(associations["mean_difference_pp"])].copy()
    shown["family_order"] = shown["feature_family"].map({"broad_all_cells": 0, "t_state_within_t": 1})
    shown["plot_key"] = shown["feature_family"] + "::" + shown["feature"]
    feature_order = (
        shown[shown["analysis_set"] == "primary_all_specimens"]
        .sort_values(["family_order", "feature"])["plot_key"]
        .tolist()
    )
    positions = np.arange(len(feature_order))
    fig, axes_grid = plt.subplots(2, 2, figsize=(15.5, max(10.0, len(feature_order) * 0.82)), sharey=True)
    axes = axes_grid.ravel()
    colors = {"broad_all_cells": "#2878b5", "t_state_within_t": "#d97904"}
    markers = {"broad_all_cells": "o", "t_state_within_t": "s"}
    x_low = float(np.nanmin(shown["ci95_low_pp"]))
    x_high = float(np.nanmax(shown["ci95_high_pp"]))
    padding = max(1.0, (x_high - x_low) * 0.06)
    panel_titles = {
        "primary_all_specimens": "All timepoints: patient means",
        "sensitivity_pre_only": "Pre only",
        "sensitivity_post_only": "Post only",
        "sensitivity_stable_anti_pd1": "Stable anti-PD1 only",
    }
    for panel_index, (ax, analysis_set) in enumerate(zip(axes, ANALYSIS_SETS)):
        panel = shown[shown["analysis_set"] == analysis_set].set_index("plot_key").reindex(feature_order).reset_index()
        for family in ("broad_all_cells", "t_state_within_t"):
            subset = panel[panel["feature_family"] == family]
            y = subset.index.to_numpy()
            effect = subset["mean_difference_pp"].to_numpy()
            low = subset["ci95_low_pp"].to_numpy()
            high = subset["ci95_high_pp"].to_numpy()
            ax.errorbar(
                effect,
                y,
                xerr=np.vstack([effect - low, high - effect]),
                fmt=markers[family],
                capsize=3,
                color=colors[family],
                label=family,
            )
        ax.axvline(0, color="#666666", linewidth=1)
        n_r = int(panel["n_responder"].max())
        n_nr = int(panel["n_non_responder"].max())
        ax.set_title(f"{panel_titles[analysis_set]}\nnR={n_r}, nNR={n_nr}")
        ax.set_xlim(x_low - padding, x_high + padding * 3.0)
        ax.set_xlabel("R − NR (percentage points)" if panel_index >= 2 else "")
        for index, row in panel.iterrows():
            q_label = f"q={row['fdr_bh_analysis_set']:.3f}" if bool(row["tested"]) else "QC only"
            ax.text(x_high + padding * 0.2, index, q_label, va="center", fontsize=7)
    y_labels = []
    for plot_key in feature_order:
        family, feature = plot_key.split("::", 1)
        family_label = "broad" if family == "broad_all_cells" else "T-state"
        y_labels.append(f"{family_label}: {feature}{' (uncertainty)' if feature == 'unknown' else ''}")
    axes[0].set_yticks(positions, y_labels)
    axes[0].invert_yaxis()
    axes[-1].legend(frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.suptitle("Exploratory recorded-response associations at patient level")
    fig.text(
        0.5,
        0.01,
        "R, responder; NR, non-responder. 95% patient bootstrap intervals; permutation p values; analysis-set-wide BH. Non-causal.",
        ha="center",
        fontsize=8,
    )
    fig.subplots_adjust(left=0.14, right=0.88, bottom=0.08, top=0.90, hspace=0.30, wspace=0.20)
    save_figure(fig, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    parser.add_argument("--bootstraps", type=int, default=DEFAULT_BOOTSTRAPS)
    args = parser.parse_args()
    if args.permutations < 100:
        raise ValueError("at_least_100_permutations_required")
    if args.bootstraps < 100:
        raise ValueError("at_least_100_bootstraps_required")

    input_path = Path(args.input).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    source_hash_before = sha256(input_path)
    adata = ad.read_h5ad(input_path)
    validate_input(adata)

    obs = adata.obs.copy()
    specimens_meta = derive_specimen_table(obs)
    patient_summary = derive_patient_summary(specimens_meta)
    validate_patient_response_metadata(obs, patient_summary)
    specimen_composition, broad_columns, t_columns = aggregate_specimen_composition(obs, specimens_meta)
    patient_timepoints = aggregate_patient_timepoints(specimen_composition, broad_columns, t_columns)
    analysis_patients = build_analysis_patient_composition(
        patient_timepoints, patient_summary, broad_columns, t_columns
    )
    associations = build_associations(
        analysis_patients,
        broad_columns,
        t_columns,
        args.permutations,
        args.bootstraps,
        args.seed,
    )
    ambiguous_ids = set(
        patient_summary.loc[patient_summary["response_status"] != "consistent", "patient_id"]
    )
    excluded = specimen_composition.loc[
        specimen_composition["patient_id"].isin(ambiguous_ids),
        ["patient_id", "specimen_id", "response", "timepoint", "therapy", "n_cells", "n_t_cells"],
    ].copy()
    excluded["exclusion_reason"] = "ambiguous_longitudinal_response"
    confounding_counts = build_confounding_counts(analysis_patients)

    specimen_composition.to_csv(outdir / "specimen_composition.csv", index=False, float_format="%.12g")
    patient_timepoints.to_csv(outdir / "patient_timepoint_composition.csv", index=False, float_format="%.12g")
    analysis_patients.to_csv(outdir / "analysis_patient_composition.csv", index=False, float_format="%.12g")
    associations.to_csv(outdir / "response_associations.csv", index=False, float_format="%.12g")
    excluded.to_csv(outdir / "excluded_patients.csv", index=False)
    confounding_counts.to_csv(outdir / "confounding_counts.csv", index=False)

    plot_umap(adata, "biodsh_broad_label", "Broad immune-cell marker programs", outdir / "umap_broad_labels.png")
    plot_umap(
        adata,
        "biodsh_t_state",
        "T-cell-state marker programs",
        outdir / "umap_t_states.png",
        only_t_cells=True,
    )
    plot_patient_composition(analysis_patients, broad_columns, outdir / "patient_broad_composition.png")
    plot_cohort_flow(patient_summary, specimen_composition, analysis_patients, outdir / "cohort_flow.png")
    plot_recorded_response_associations(associations, outdir / "recorded_response_associations.png")

    source_hash_after = sha256(input_path)
    group_sizes = {}
    for analysis_set in ANALYSIS_SETS:
        counts = analysis_patients.loc[
            analysis_patients["analysis_set"] == analysis_set, "response"
        ].value_counts()
        group_sizes[analysis_set] = {label: int(counts.get(label, 0)) for label in RESPONSE_LABELS}
    report = {
        "schema_version": "1.0",
        "input": {
            "path": input_path.name,
            "path_scope": "basename_only_for_portable_reporting",
            "sha256_before": source_hash_before,
            "sha256_after": source_hash_after,
            "source_unchanged": source_hash_before == source_hash_after,
            "cells": int(adata.n_obs),
            "genes": int(adata.n_vars),
            "patients": int(patient_summary["patient_id"].nunique()),
            "specimens": int(specimen_composition["specimen_id"].nunique()),
        },
        "upstream_annotation": {
            "clinical_metadata_used_for_labels": bool(adata.uns["biodsh_annotation"]["clinical_metadata_used"]),
            "biological_reference_kind": adata.uns["biodsh_annotation"].get("biological_reference_kind"),
            "labels_frozen_before_response_use": True,
        },
        "aggregation": {
            "specimen_first": True,
            "patient_timepoint_intermediate": True,
            "specimen_weighting_within_patient_timepoint": "equal",
            "timepoint_weighting_within_patient": "equal",
            "inferential_unit": "patient",
            "cell_level_inference": False,
            "pseudoreplication_guard": True,
            "broad_denominator": "all_cells_within_specimen",
            "t_state_denominator": "T_cells_within_specimen",
            "minimum_total_cells_for_broad": MIN_TOTAL_CELLS,
            "minimum_t_cells_for_t_state": MIN_T_CELLS,
        },
        "analysis_sets": ANALYSIS_SETS,
        "group_sizes": group_sizes,
        "features": {
            "broad_all_cells": broad_columns,
            "t_state_within_t": t_columns,
            "quality_control_only": [
                column for column in broad_columns + t_columns if column.endswith("__unknown")
            ],
        },
        "inference": {
            "effect": "responder_minus_non_responder_mean_proportion",
            "permutation_test": "two_sided_patient_label_permutation",
            "permutations": int(args.permutations),
            "exact_permutation_max_unique_labelings": MAX_EXACT_PERMUTATIONS,
            "confidence_interval": "patient_bootstrap_percentile_95",
            "bootstraps": int(args.bootstraps),
            "multiple_testing": "Benjamini-Hochberg_across_all_tested_features_within_analysis_set",
            "additional_effect_size": "Cliffs_delta",
            "seed": int(args.seed),
        },
        "longitudinal_response_ambiguity": {
            "response_label_scope": "specimen_record",
            "excluded_from_all_inference": True,
            "patients": sorted(ambiguous_ids, key=natural_key),
            "patient_count": int(len(ambiguous_ids)),
            "specimen_count": int(len(excluded)),
        },
        "claim_boundaries": {
            "clinical_claim_allowed": False,
            "causal_claim_allowed": False,
            "treatment_efficacy_claim_allowed": False,
            "predictive_validation_claim_allowed": False,
            "moderna_trial_data": False,
            "statement": (
                "Exploratory composition associations in a public checkpoint-immunotherapy proxy dataset; "
                "annotations are marker-program hypotheses and categories are compositionally dependent."
            ),
        },
        "figures": [
            "umap_broad_labels.png",
            "umap_t_states.png",
            "patient_broad_composition.png",
            "cohort_flow.png",
            "recorded_response_associations.png",
        ],
        "versions": {name: version(name) for name in ("anndata", "matplotlib", "numpy", "pandas")},
    }
    (outdir / "treatment_response_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "patients_in_primary": sum(group_sizes["primary_all_specimens"].values()),
                "ambiguous_patients_excluded": sorted(ambiguous_ids, key=natural_key),
                "tested_associations": int(associations["tested"].sum()),
            }
        )
    )


if __name__ == "__main__":
    main()
