"""BioDSH skill: 分子对接虚拟筛选 (AutoDock Vina).

Dock a set of small-molecule ligands (SMILES or SDF) into a receptor pocket with
AutoDock Vina and rank the hits by predicted binding affinity.

Pipeline
--------
1. Receptor -> PDBQT (used as-is if already .pdbqt; otherwise Meeko
   `mk_prepare_receptor`, else Open Babel `obabel -xr`).
2. Determine the Vina search box from --center (x,y,z) or --ref-ligand (centroid).
3. For each ligand:
     SMILES -> 3D conformer (RDKit ETKDGv3 + MMFF/UFF optimize) -> PDBQT (Meeko)
     (SDF molecules are used directly if they already carry 3D coordinates.)
     -> Vina dock -> best affinity (kcal/mol) + best pose saved.
4. Write docking_scores.csv (ranked ascending), poses/, docking_top.png,
   docking_summary.json.

Heavy dependencies are NOT in the base analysis env. Install them with:

    uv pip install vina meeko rdkit

The imports below are guarded: if a package is missing the script prints the
exact install command and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- guarded imports -------------------------------------------------------
# RDKit (SMILES/SDF -> 3D), Meeko (ligand -> PDBQT) and Vina (docking) are all
# heavy and are not preinstalled. Fail loudly with the exact install command.
_MISSING = []
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.*")  # silence RDKit's verbose C++ logging
except ImportError:
    _MISSING.append("rdkit")

try:
    import meeko  # noqa: F401  (submodules imported lazily in ligand_to_pdbqt)
except ImportError:
    _MISSING.append("meeko")

try:
    from vina import Vina
except ImportError:
    _MISSING.append("vina")

if _MISSING:
    print(
        json.dumps(
            {
                "error": (
                    "Missing packages for molecular docking: "
                    + ", ".join(_MISSING)
                    + ". Install them with:  uv pip install vina meeko rdkit"
                )
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

# matplotlib only for the summary barplot; keep it headless.
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def parse_triple(text: str, name: str) -> list[float]:
    """Parse a comma-separated 'x,y,z' triple into three floats."""
    parts = [p.strip() for p in text.replace(" ", "").split(",") if p.strip() != ""]
    if len(parts) != 3:
        raise ValueError(f"--{name} must be three comma-separated numbers, got {text!r}")
    try:
        return [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"--{name} contains a non-number: {text!r}") from exc


def centroid_from_file(path: Path) -> list[float]:
    """Geometric center of a bound-ligand file, used to place the search box.

    Handles .pdb/.pdbqt by reading ATOM/HETATM coordinate columns, and any
    RDKit-readable format (.sdf/.mol/.mol2) via its conformer coordinates.
    """
    suffix = path.suffix.lower()
    coords: list[tuple[float, float, float]] = []

    if suffix in (".pdb", ".pdbqt", ".ent"):
        for line in path.read_text(errors="ignore").splitlines():
            if line.startswith(("ATOM", "HETATM")):
                try:
                    x = float(line[30:38])
                    y = float(line[38:46])
                    z = float(line[46:54])
                except ValueError:
                    continue
                coords.append((x, y, z))
    else:
        mol = None
        if suffix in (".sdf", ".mol"):
            supplier = Chem.SDMolSupplier(str(path), removeHs=False)
            for m in supplier:
                if m is not None:
                    mol = m
                    break
        elif suffix == ".mol2":
            mol = Chem.MolFromMol2File(str(path), removeHs=False)
        if mol is None or mol.GetNumConformers() == 0:
            raise ValueError(f"Could not read 3D coordinates from --ref-ligand {path}")
        conf = mol.GetConformer()
        for i in range(mol.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            coords.append((p.x, p.y, p.z))

    if not coords:
        raise ValueError(f"No atom coordinates found in --ref-ligand {path}")
    n = len(coords)
    return [sum(c[i] for c in coords) / n for i in range(3)]


def prepare_receptor(receptor: Path, outdir: Path) -> Path:
    """Return a receptor .pdbqt, converting from .pdb if needed.

    Order of attempts: use as-is if already .pdbqt; Meeko `mk_prepare_receptor`
    CLI; Open Babel `obabel -xr`. If none is available, fail with instructions.
    """
    if receptor.suffix.lower() == ".pdbqt":
        return receptor

    out_pdbqt = outdir / (receptor.stem + ".pdbqt")

    # 1) Meeko receptor prep CLI (installed with meeko as mk_prepare_receptor.py)
    for exe in ("mk_prepare_receptor.py", "mk_prepare_receptor"):
        if shutil.which(exe):
            try:
                subprocess.run(
                    [exe, "--read_pdb", str(receptor), "-o", str(out_pdbqt.with_suffix("")),
                     "-p"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # mk_prepare_receptor writes <stem>.pdbqt
                if out_pdbqt.exists():
                    return out_pdbqt
            except subprocess.CalledProcessError:
                pass  # fall through to obabel

    # 2) Open Babel receptor prep
    if shutil.which("obabel"):
        subprocess.run(
            ["obabel", str(receptor), "-xr", "-O", str(out_pdbqt)],
            check=True,
            capture_output=True,
            text=True,
        )
        if out_pdbqt.exists():
            return out_pdbqt

    raise RuntimeError(
        "Cannot convert the receptor to PDBQT: neither Meeko's "
        "'mk_prepare_receptor' nor Open Babel 'obabel' is on PATH. Either pass a "
        "prepared '--receptor receptor.pdbqt', or convert it yourself, e.g.:\n"
        f"    mk_prepare_receptor.py --read_pdb {receptor} -o {receptor.stem} -p\n"
        f"    # or\n"
        f"    obabel {receptor} -xr -O {receptor.stem}.pdbqt"
    )


def mol_to_pdbqt_string(mol) -> str:
    """Convert an embedded, H-added RDKit mol to a Vina-ready PDBQT string.

    Supports both the modern Meeko API (>=0.5, PDBQTWriterLegacy) and the older
    0.4 API (write_pdbqt_string)."""
    from meeko import MoleculePreparation

    prep = MoleculePreparation()
    setups = prep.prepare(mol)

    # Modern API returns a list of MoleculeSetup objects.
    if isinstance(setups, (list, tuple)) and setups:
        from meeko import PDBQTWriterLegacy

        pdbqt_string, is_ok, err = PDBQTWriterLegacy.write_string(setups[0])
        if not is_ok:
            raise RuntimeError(f"Meeko failed to write PDBQT: {err}")
        return pdbqt_string

    # Legacy 0.4 API: prepare() mutated `prep` in place.
    return prep.write_pdbqt_string()


def smiles_to_mol3d(smiles: str, seed: int):
    """SMILES -> RDKit mol with one optimized 3D conformer, or None on failure."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(mol, params) != 0:
        # Retry with random coordinates for awkward molecules.
        params.useRandomCoords = True
        if AllChem.EmbedMolecule(mol, params) != 0:
            return None
    # Prefer MMFF, fall back to UFF.
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        else:
            AllChem.UFFOptimizeMolecule(mol, maxIters=500)
    except Exception:
        pass  # an unoptimized-but-embedded conformer is still dockable
    return mol


def iter_ligands(path: Path):
    """Yield (ligand_id, smiles, rdkit_mol_or_None) for each input ligand.

    - .sdf: molecules read directly (3D used as-is when present, else embedded).
    - .smi/.csv/.txt: one ligand per line; the SMILES token is auto-detected so
      both 'name,SMILES' and 'SMILES name' layouts (and headers) work.
    """
    suffix = path.suffix.lower()

    if suffix == ".sdf":
        supplier = Chem.SDMolSupplier(str(path), removeHs=False)
        for idx, mol in enumerate(supplier):
            if mol is None:
                yield (f"lig{idx + 1}", None, None)
                continue
            name = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else ""
            lig_id = name or f"lig{idx + 1}"
            try:
                smi = Chem.MolToSmiles(Chem.RemoveHs(mol))
            except Exception:
                smi = ""
            yield (lig_id, smi, mol)
        return

    # Text formats: parse line by line.
    for idx, raw in enumerate(path.read_text(errors="ignore").splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Split on comma or whitespace.
        tokens = [t for t in line.replace(",", " ").split() if t]
        if not tokens:
            continue
        # Skip an obvious header row.
        if idx == 0 and any(t.lower() in ("smiles", "name", "id", "ligand") for t in tokens):
            continue
        # Auto-detect which token is the SMILES (the first that RDKit can parse).
        smi = None
        name = None
        for t in tokens:
            if smi is None and Chem.MolFromSmiles(t) is not None:
                smi = t
            else:
                name = name or t
        if smi is None:
            # Whole line unparseable; report it so the caller logs a failure.
            yield (name or f"lig{idx + 1}", tokens[0], None)
            continue
        lig_id = name or f"lig{idx + 1}"
        yield (lig_id, smi, None)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Virtual screening by molecular docking with AutoDock Vina."
    )
    parser.add_argument("--receptor", required=True, help="Receptor .pdb or .pdbqt")
    parser.add_argument(
        "--ligands", required=True, help="Ligands: .smi/.csv/.txt of SMILES, or .sdf"
    )
    parser.add_argument("--center", help="Search-box center 'x,y,z' in Angstrom")
    parser.add_argument(
        "--ref-ligand",
        dest="ref_ligand",
        help="Bound-ligand file; box center is its centroid (alternative to --center)",
    )
    parser.add_argument("--box-size", dest="box_size", default="20,20,20",
                        help="Search-box size 'sx,sy,sz' in Angstrom (default 20,20,20)")
    parser.add_argument("--exhaustiveness", type=int, default=8,
                        help="Vina exhaustiveness (default 8)")
    parser.add_argument("--n-poses", dest="n_poses", type=int, default=1,
                        help="Number of poses to search/keep (default 1)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    parser.add_argument("--max-ligands", dest="max_ligands", type=int, default=0,
                        help="Cap the number of ligands (0 = no cap); handy for a test run")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()

    receptor = Path(args.receptor)
    ligands = Path(args.ligands)
    if not receptor.exists():
        print(json.dumps({"error": f"receptor not found: {receptor}"}))
        sys.exit(1)
    if not ligands.exists():
        print(json.dumps({"error": f"ligands file not found: {ligands}"}))
        sys.exit(1)

    outdir = Path(args.outdir)
    poses_dir = outdir / "poses"
    poses_dir.mkdir(parents=True, exist_ok=True)

    # --- box geometry ------------------------------------------------------
    try:
        box_size = parse_triple(args.box_size, "box-size")
        if args.center:
            center = parse_triple(args.center, "center")
        elif args.ref_ligand:
            ref = Path(args.ref_ligand)
            if not ref.exists():
                raise ValueError(f"--ref-ligand not found: {ref}")
            center = centroid_from_file(ref)
        else:
            raise ValueError("provide either --center X,Y,Z or --ref-ligand FILE")
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)

    # --- receptor prep -----------------------------------------------------
    try:
        receptor_pdbqt = prepare_receptor(receptor, outdir)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        msg = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(json.dumps({"error": f"receptor preparation failed: {msg}"}))
        sys.exit(1)

    # --- Vina setup (receptor + maps computed once, reused per ligand) ------
    t0 = time.time()
    v = Vina(sf_name="vina", seed=args.seed, verbosity=0)
    v.set_receptor(str(receptor_pdbqt))
    v.compute_vina_maps(center=center, box_size=box_size)

    results: list[dict] = []
    failed: list[dict] = []
    n_seen = 0

    for lig_id, smiles, mol in iter_ligands(ligands):
        if args.max_ligands and n_seen >= args.max_ligands:
            break
        n_seen += 1

        # Ensure we have an embedded, H-added 3D mol.
        try:
            if mol is None:
                if not smiles:
                    raise ValueError("no SMILES / molecule")
                mol = smiles_to_mol3d(smiles, args.seed)
                if mol is None:
                    raise ValueError("3D embedding failed")
            else:
                # SDF-derived: make sure it has hydrogens and a conformer.
                if mol.GetNumConformers() == 0:
                    remade = smiles_to_mol3d(smiles, args.seed) if smiles else None
                    if remade is None:
                        raise ValueError("no 3D conformer in SDF and no SMILES to rebuild")
                    mol = remade
                else:
                    mol = Chem.AddHs(mol, addCoords=True)

            ligand_pdbqt = mol_to_pdbqt_string(mol)
        except Exception as exc:  # noqa: BLE001 - log and skip, keep screening
            failed.append({"ligand_id": lig_id, "smiles": smiles, "reason": str(exc)})
            print(f"[skip] {lig_id}: {exc}", file=sys.stderr)
            continue

        # Dock.
        try:
            v.set_ligand_from_string(ligand_pdbqt)
            v.dock(exhaustiveness=args.exhaustiveness, n_poses=args.n_poses)
            energies = v.energies(n_poses=1)
            best_affinity = float(energies[0][0])  # first column = total affinity
            # Meeko/Vina PDBQT ids may contain path-unfriendly chars; sanitize.
            safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in lig_id)
            pose_path = poses_dir / f"{safe_id}.pdbqt"
            v.write_poses(str(pose_path), n_poses=1, overwrite=True)
        except Exception as exc:  # noqa: BLE001
            failed.append({"ligand_id": lig_id, "smiles": smiles, "reason": f"dock: {exc}"})
            print(f"[skip] {lig_id}: dock failed: {exc}", file=sys.stderr)
            continue

        results.append(
            {
                "ligand_id": lig_id,
                "smiles": smiles,
                "best_affinity_kcal_mol": round(best_affinity, 3),
                "pose": str(pose_path),
            }
        )
        print(f"[ok]   {lig_id}: {best_affinity:.2f} kcal/mol", file=sys.stderr)

    # --- rank & write scores ----------------------------------------------
    results.sort(key=lambda r: r["best_affinity_kcal_mol"])  # ascending (most negative first)

    scores_csv = outdir / "docking_scores.csv"
    with scores_csv.open("w", encoding="utf-8") as fh:
        fh.write("ligand_id,smiles,best_affinity_kcal_mol\n")
        for r in results:
            smi = (r["smiles"] or "").replace(",", "")  # keep CSV single-column-safe
            fh.write(f"{r['ligand_id']},{smi},{r['best_affinity_kcal_mol']}\n")

    # --- top-hits barplot --------------------------------------------------
    top_png = outdir / "docking_top.png"
    if results:
        top = results[: min(15, len(results))]
        labels = [r["ligand_id"] for r in top]
        vals = [r["best_affinity_kcal_mol"] for r in top]
        fig, ax = plt.subplots(figsize=(max(5, 0.5 * len(top)), 4))
        ax.bar(range(len(top)), vals, color="#2b6cb0")
        ax.set_xticks(range(len(top)))
        ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
        ax.set_ylabel("Best affinity (kcal/mol)")
        ax.set_title("Top docking hits (lower = stronger)")
        ax.invert_yaxis()  # strongest (most negative) bar reads as tallest
        fig.tight_layout()
        fig.savefig(top_png, dpi=150)
        plt.close(fig)

    # --- summary -----------------------------------------------------------
    wall = round(time.time() - t0, 1)
    summary = {
        "receptor": str(receptor),
        "receptor_pdbqt": str(receptor_pdbqt),
        "box_center": center,
        "box_size": box_size,
        "exhaustiveness": args.exhaustiveness,
        "seed": args.seed,
        "n_ligands_seen": n_seen,
        "n_docked": len(results),
        "n_failed": len(failed),
        "wall_time_sec": wall,
        "top10": results[:10],
        "failed": failed,
        "outputs": ["docking_scores.csv", "poses/", "docking_top.png", "docking_summary.json"],
    }
    (outdir / "docking_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- short ranked summary to stdout ------------------------------------
    print("DOCKING_SKILL_OK "
          + json.dumps({"n_docked": len(results), "n_failed": len(failed),
                        "wall_time_sec": wall}, ensure_ascii=False))
    print(f"Ranked {len(results)} ligand(s) (skipped {len(failed)}), {wall}s:")
    for i, r in enumerate(results[:10], 1):
        print(f"  {i:>2}. {r['ligand_id']:<20} {r['best_affinity_kcal_mol']:>7.2f} kcal/mol")
    print(f"Scores: {scores_csv}")


if __name__ == "__main__":
    main()
