---
name: md-simulation
description: Run a short molecular dynamics simulation of a protein (optionally a protein-ligand complex) with OpenMM — fix the structure, minimize, equilibrate, run a brief production trajectory, and report backbone RMSD stability over time. Use to relax/equilibrate a structure and check its stability, not for long production MD or free-energy calculations.
---

# Molecular dynamics simulation (OpenMM)

Use this skill when the user wants to **relax and equilibrate a protein structure and check how stable it is** — e.g. clean up a homology model or a docked pose, remove clashes, and see whether the backbone holds together over a short trajectory. Good follow-up to the `drug-docking` skill for sanity-checking a complex.

Do **not** use it for: long production MD (µs), binding free-energy / FEP, or docking (use `drug-docking`). The defaults here are deliberately short so a run finishes in minutes on a laptop.

## Install the heavy libraries first (compute-heavy)

The base analysis env does **not** ship the MD stack. Install it once with the app's package tool before the first run:

```bash
uv pip install openmm pdbfixer mdtraj
```

- `openmm` — the MD engine and force fields.
- `pdbfixer` — repairs the input structure (missing atoms/residues, hydrogens).
- `mdtraj` — reads the trajectory and computes RMSD.

Notes: OpenMM is **compute-heavy**; it is easiest and fastest via conda/mamba (`mamba install -c conda-forge openmm pdbfixer mdtraj`), which also pulls in CUDA/OpenCL support for GPU speed, but pip wheels exist and work on CPU. The script auto-selects the fastest available platform (CUDA > OpenCL > CPU) and falls back to CPU if no accelerator is present.

## Required inputs

- `--pdb` — the protein structure (`.pdb`). If it contains a bound ligand/hetero groups you can keep or drop them (`--keep-hetero`, `--keep-water`); by default heterogens and water are removed and only the protein is simulated.

## Exact run command

```bash
bioenv/.venv/bin/python "<skill dir>/run.py" \
  --pdb protein.pdb \
  --solvent implicit \
  --steps 50000 \
  --temperature 300 \
  --outdir md_out
```

Options and defaults:

- `--ff` (default `amber14-all.xml amber14/tip3pfb.xml`) — force-field XML files; accepts several, space-separated. For **implicit** solvent an implicit model XML (`implicit/gbn2.xml`) is added automatically.
- `--solvent implicit|explicit` (default `implicit`) — implicit GBn2 is much faster and is the default; `explicit` builds a TIP3P water box (slower, more realistic).
- `--steps N` (default `50000` ≈ 100 ps at 2 fs) — production steps. **Scale up** for real work: 500,000 steps ≈ 1 ns, 5,000,000 ≈ 10 ns; expect roughly linear wall-time.
- `--temperature K` (default `300`).
- `--equil-steps N` (default `5000`), `--report-interval N` (default `1000` steps between trajectory/log frames), `--dt-fs` (default `2.0`), `--seed`, `--keep-water`, `--keep-hetero`.

## Reading the outputs

Everything lands in `--outdir`:

- `minimized.pdb` — the fixed, energy-minimized starting structure (and the RMSD reference frame).
- `trajectory.dcd` — the production trajectory (open with `minimized.pdb` as topology).
- `energy_log.csv` — per-frame step, potential energy (kJ/mol), temperature (K), elapsed time.
- `rmsd.csv` — backbone RMSD (nm) vs the minimized frame, per trajectory frame, with a time (ps) column.
- `rmsd.png` — RMSD over time; the curve should **rise then plateau** if the structure is stable.
- `md_summary.json` — n_atoms, steps, dt, temperature, solvent, platform, final/mean RMSD, wall-time.

The script prints a short summary to stdout. Report the mean/final RMSD and the absolute path of `rmsd.png`.

## Caveats

- A flat, low RMSD plateau (a few Å) suggests a **stable** structure; a curve that keeps climbing suggests it is unfolding or the model/pose is poor — do not over-interpret a short run either way.
- Implicit solvent (default) trades accuracy for speed; for publication-grade dynamics use `--solvent explicit` and far more steps.
- If PDBFixer cannot parse or repair the input (badly broken PDB, non-standard residues, missing a matching force field), the script exits with a clear error — clean the structure or supply the right `--ff`.
- Ligand parameters are **not** auto-generated: an arbitrary small molecule kept via `--keep-hetero` will usually fail force-field matching. For protein–ligand MD you must supply ligand parameters (e.g. GAFF/OpenFF) — out of scope for this quick skill.
