#!/usr/bin/env bash
# WSL + Windows R replay; explicit writes only to this skill and the scratch path.
set -euo pipefail
skill_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
strata_scratch=${1:-/mnt/c/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-strata}
strata_python=${STRATA_PYTHON:-/home/moliex-desktop/bench/env/bin/python}
strata_rscript=${STRATA_RSCRIPT:-/mnt/c/Program Files/R/R-4.6.0/bin/Rscript.exe}
mkdir -p "$strata_scratch/data" "$strata_scratch/r-output" "$strata_scratch/r-tmp" "$skill_dir/validation/results"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
"$strata_python" "$skill_dir/validation/make_data.py" "$strata_scratch/data"
strata_rtemp=$(wslpath -m "$strata_scratch/r-tmp")
env R_LIMMA_LIB="${R_LIMMA_LIB:-C:/Users/MOLIEX-DESKTOP/bench-rlib}" \
    TMPDIR="$strata_rtemp" TMP="$strata_rtemp" TEMP="$strata_rtemp" \
    WSLENV="${WSLENV:+$WSLENV:}R_LIMMA_LIB:TMPDIR:TMP:TEMP" \
    "$strata_rscript" "$(wslpath -m "$skill_dir/validation/anova_ref.R")" \
    "$(wslpath -m "$strata_scratch/data")" "$(wslpath -m "$strata_scratch/r-output")" \
    > "$skill_dir/validation/r_run.log" 2>&1
"$strata_python" "$skill_dir/validation/compare.py" "$strata_scratch/data" "$strata_scratch/r-output" "$skill_dir/validation/results" \
    > "$skill_dir/validation/compare_run.log" 2>&1
"$strata_python" "$skill_dir/validation/check_edges.py" "$strata_scratch/data" "$skill_dir/validation/results/edges_timing.json" \
    > "$skill_dir/validation/edges_run.log" 2>&1
mkdir -p "$skill_dir/validation/data" "$skill_dir/validation/r-reference"
cp "$strata_scratch/data/"*.csv "$skill_dir/validation/data/"
cp "$strata_scratch/r-output/"*.csv "$strata_scratch/r-output/versions.txt" "$skill_dir/validation/r-reference/"
head -n 1 "$skill_dir/validation/compare_run.log"
cat "$skill_dir/validation/edges_run.log"
