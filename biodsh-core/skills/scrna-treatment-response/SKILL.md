---
name: scrna-treatment-response
description: Compare immune-cell compositions between response groups using patient-level aggregation, deterministic inference, and explicit longitudinal-label safeguards.
---

# scRNA-seq treatment-response association

Use this skill after outcome-blind cell-state annotation when an AnnData `.h5ad` input contains specimen, patient, response, therapy, timepoint, broad-cell, T-cell-state, and two-dimensional UMAP fields. If `patient_response` is present, cross-check it against response values rederived from specimen records rather than trusting it.

## Scientific contract

- Treat the source file as read-only and verify its SHA-256 before and after execution.
- Require upstream annotations to declare that clinical metadata was not used for cell labeling. Use response labels only after those labels are frozen.
- Validate that patient, response, therapy, and timepoint are internally consistent within each specimen.
- Derive patient response from specimen records. Exclude patients with conflicting longitudinal response labels from every responder/non-responder test and report them separately.
- Calculate cell compositions per specimen first, average specimens equally within patient/timepoint, then average timepoints equally within patient. Never use cells as independent inferential units.
- Require at least 100 total cells for broad composition and 50 T cells for T-state composition; below-threshold values remain auditable but do not enter that feature family.
- Use the patient-level all-timepoint average as the primary exploratory analysis, with pre-treatment-only, post-treatment-only, and stable anti-PD1-only sensitivity analyses.
- Compare responder and non-responder patient compositions using seeded two-sided label-permutation tests, patient bootstrap confidence intervals, Cliff's delta, and one Benjamini-Hochberg correction across all tested biological features within each analysis set.
- Report every category and preserve the compositional dependence among categories in the claim boundary. Treat `unknown` as a QC-only uncertainty control and exclude it from hypothesis tests and FDR.
- Treat associations as exploratory and non-causal. Do not claim treatment efficacy, prediction, clinical validation, or analysis of a Moderna trial.

## Outputs

- `specimen_composition.csv`: one row per specimen with metadata and broad/T-state proportions.
- `patient_timepoint_composition.csv`: the auditable patient/timepoint intermediate after equal-specimen aggregation.
- `analysis_patient_composition.csv`: one row per included patient and analysis set, after equal-timepoint aggregation.
- `response_associations.csv`: patient-level effect sizes, bootstrap intervals, permutation p-values, and analysis-set-wide FDR.
- `excluded_patients.csv`: specimen-level records for patients excluded because longitudinal response labels conflict.
- `confounding_counts.csv`: response-stratified counts of therapy and timepoint profiles.
- `treatment_response_report.json`: input integrity, aggregation, inference, group sizes, safeguards, versions, and claim boundaries.
- `umap_broad_labels.png` and `umap_t_states.png`: outcome-blind annotation maps.
- `patient_broad_composition.png`: all-specimen and pre-treatment patient-level broad-cell composition.
- `cohort_flow.png`: patient/specimen cohort flow and explicit ambiguity exclusion.
- `recorded_response_associations.png`: primary and timepoint-sensitivity associations with uncertainty.
