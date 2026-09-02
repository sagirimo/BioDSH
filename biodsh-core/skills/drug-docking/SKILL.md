---
name: drug-docking
description: Virtual screening by molecular docking with AutoDock Vina — dock a set of small-molecule ligands (given as SMILES in a .smi/.csv/.txt file, or as an .sdf) into a receptor pocket, rank the hits by predicted binding affinity (kcal/mol) and save the best pose for each ligand. Use for structure-based drug screening / hit finding, not for ligand-based similarity search.
---

# Molecular docking virtual screening (AutoDock Vina)

Use this skill when the user wants to **dock small molecules into a protein pocket and rank them by binding affinity** — structure-based virtual screening, hit triage, or re-scoring a candidate series against one receptor. You need a receptor structure and a set of ligands (SMILES or an SDF of 3D molecules).

Do **not** use it for: ligand-based similarity/QSAR (no receptor), protein–protein docking, or free-energy / MD refinement (use the `md-simulation` skill to relax a complex afterwards).

## Install the heavy libraries first (compute-heavy)

The base analysis env does **not** ship the docking stack. Install it once with the app's package tool before the first run:

```bash
uv pip install vina meeko rdkit
```

- `vina` — AutoDock Vina Python bindings (the docking engine).
- `meeko` — prepares ligand and receptor PDBQT files (atom typing, torsions, Gasteiger charges).
- `rdkit` — turns SMILES into a sensible 3D conformer before docking.

This is **compute-heavy**: each ligand runs a full Vina search. Time scales with `--exhaustiveness` and the number of ligands. Screen a handful first to check the box, then scale up. If `vina`'s wheel is unavailable on the platform, it can also be built from source or installed via conda (`conda install -c conda-forge vina`); `meeko`/`rdkit` install cleanly from pip.

## Required inputs

- `--receptor` — the target, as `.pdb` or `.pdbqt`. A `.pdbqt` is used directly. A `.pdb` is auto-converted to PDBQT (Meeko `mk_prepare_receptor` if available, else Open Babel `obabel -xr`). If neither tool is present the script tells you the exact command to prepare it yourself.
- `--ligands` — the library to screen: a `.smi` / `.csv` / `.txt` of SMILES (optionally `name,SMILES` or `SMILES name`, with or without a header) **or** an `.sdf` of 3D molecules.
- The **search box** — required, one of:
  - `--center X,Y,Z` (Å, e.g. the pocket centroid), or
  - `--ref-ligand FILE` (a bound ligand as `.pdb/.pdbqt/.sdf/.mol/.mol2`) to auto-derive the box center from its geometric center.

## Exact run command

```bash
bioenv/.venv/bin/python "<skill dir>/run.py" \
  --receptor receptor.pdb \
  --ligands ligands.smi \
  --ref-ligand crystal_ligand.sdf \
  --box-size 20,20,20 \
  --exhaustiveness 8 \
  --outdir docking_out
```

Or with an explicit box center instead of a reference ligand:

```bash
bioenv/.venv/bin/python "<skill dir>/run.py" \
  --receptor receptor.pdbqt --ligands library.csv \
  --center 12.5,3.0,-8.7 --box-size 22,22,22 --exhaustiveness 16 --outdir docking_out
```

Options: `--box-size sx,sy,sz` (Å, default `20,20,20`), `--exhaustiveness N` (default `8`; raise for harder pockets), `--n-poses N` (poses to search, default `1`), `--seed N` (default `42`, for reproducibility), `--max-ligands N` (cap for a quick test run).

## Reading the outputs

Everything lands in `--outdir`:

- `docking_scores.csv` — `ligand_id, smiles, best_affinity_kcal_mol`, **sorted ascending** (most negative = strongest predicted binder first). This is the ranking to report.
- `poses/<ligand_id>.pdbqt` — the best docked pose per ligand (view in PyMOL/Chimera on top of the receptor).
- `docking_top.png` — barplot of the top hits by affinity.
- `docking_summary.json` — receptor, box center + size, exhaustiveness, `n_ligands` attempted / succeeded / failed, and the `top10`.

The script prints a short ranked summary to stdout. Report the top hits and the absolute path of `docking_scores.csv`.

## Caveats

- Vina scores are a **rough estimate**, not a measured binding free energy. Use them to rank and triage, then confirm the top hits by a better method (MD/MM-GBSA, or experiment). Differences of a few tenths of a kcal/mol are noise.
- **Garbage box, garbage result.** The pose is only meaningful if the box actually encloses the pocket. Prefer `--ref-ligand` from a known bound structure; otherwise verify `--center` visually.
- Ligands that fail 3D embedding or PDBQT prep are **skipped and logged** (see `n_failed` and stderr), not silently dropped — the run continues.
- The receptor is treated as **rigid** and protonation/tautomer states are taken as given. For a serious campaign, prepare the receptor (protonation, flips) beforehand and pass a curated `.pdbqt`.
- Docking assumes a prepared, sensible input structure; it does not fix missing loops or clashes.
