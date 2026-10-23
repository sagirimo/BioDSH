#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
scratch=/mnt/c/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-survival
mkdir -p "$scratch/tmp"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export R_LIMMA_LIB='C:/Users/MOLIEX-DESKTOP/bench-rlib'
export TMPDIR='C:/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-survival/tmp'
export TMP="$TMPDIR" TEMP="$TMPDIR" WSLENV="${WSLENV:+$WSLENV:}R_LIMMA_LIB:TMPDIR:TMP:TEMP"
py=/home/moliex-desktop/bench/env/bin/python
"$py" "$here/make_data.py" "$scratch"
'/mnt/c/Program Files/R/R-4.6.0/bin/Rscript.exe' --vanilla "$(wslpath -w "$here/survival_ref.R")" 'C:/Users/MOLIEX-DESKTOP/bench-codex-scratch/skill-survival' > "$scratch/r_run.log" 2>&1
"$py" "$here/compare.py" "$scratch"

"$py" "$here/check_properties.py" "$scratch"
"$py" "$here/summarize.py" "$scratch"
