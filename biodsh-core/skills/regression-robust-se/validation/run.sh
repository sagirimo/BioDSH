#!/usr/bin/env bash
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")/.." && pwd)"
scratch="${SANDWICH_SCRATCH:-/mnt/c/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-sandwich}"
python_bin="${PYTHON_BIN:-$HOME/bench/env/bin/python}"
rscript="${RSCRIPT:-/mnt/c/Program Files/R/R-4.6.0/bin/Rscript.exe}"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p "$scratch/data" "$scratch/reference" "$scratch/r-temp"
export TMPDIR="$scratch/r-temp"
export TMP="$(wslpath -w "$scratch/r-temp")"
export TEMP="$TMP"
export R_LIMMA_LIB="${R_LIMMA_LIB:-C:/Users/MOLIEX-DESKTOP/bench-rlib}"
export WSLENV="${WSLENV:+$WSLENV:}R_LIMMA_LIB:TMP:TEMP"
"$python_bin" "$skill_dir/validation/make_data.py" "$scratch/data"
"$rscript" "$(wslpath -w "$skill_dir/validation/reference.R")" "$(wslpath -w "$scratch/data")" "$(wslpath -w "$scratch/reference")"
"$python_bin" "$skill_dir/validation/compare.py" "$scratch/data" "$scratch/reference" "$skill_dir/validation"
"$python_bin" "$skill_dir/validation/checks.py" "$skill_dir/validation"
"$python_bin" "$skill_dir/validation/summarize.py" "$scratch/reference"
