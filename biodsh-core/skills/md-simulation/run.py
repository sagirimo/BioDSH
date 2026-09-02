"""BioDSH skill: 分子动力学模拟 (OpenMM).

Run a short molecular dynamics simulation of a protein (optionally a
protein-ligand complex) with OpenMM: fix the structure, build a system, minimize,
briefly equilibrate, run a short production trajectory, and report backbone RMSD
stability over time.

Pipeline
--------
1. PDBFixer: add missing residues/atoms/hydrogens; optionally drop water/hetero.
2. Build System:
     implicit -> amber14 + GBn2 (fast, default)
     explicit -> amber14 + TIP3P water box
3. LangevinMiddleIntegrator; pick the fastest OpenMM Platform (CUDA/OpenCL/CPU).
4. Energy minimize -> save minimized.pdb (also the RMSD reference).
5. Short equilibration, then production writing trajectory.dcd + energy_log.csv.
6. mdtraj: backbone RMSD vs the minimized frame -> rmsd.csv + rmsd.png.
7. Write md_summary.json and print a short summary.

Heavy dependencies are NOT in the base analysis env. Install them with:

    uv pip install openmm pdbfixer mdtraj

(OpenMM is easiest/fastest via conda:  mamba install -c conda-forge openmm pdbfixer mdtraj)

The imports below are guarded: if a package is missing the script prints the
exact install command and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# --- guarded imports -------------------------------------------------------
# OpenMM (engine + force fields), PDBFixer (structure repair) and mdtraj (RMSD)
# are heavy and not preinstalled. Fail loudly with the exact install command.
_MISSING = []
try:
    import openmm as mm
    from openmm import app, unit
except ImportError:
    _MISSING.append("openmm")

try:
    from pdbfixer import PDBFixer
except ImportError:
    _MISSING.append("pdbfixer")

try:
    import mdtraj as md
except ImportError:
    _MISSING.append("mdtraj")

if _MISSING:
    print(
        json.dumps(
            {
                "error": (
                    "Missing packages for MD simulation: "
                    + ", ".join(_MISSING)
                    + ". Install them with:  uv pip install openmm pdbfixer mdtraj"
                    + "  (or, easier/faster: mamba install -c conda-forge openmm pdbfixer mdtraj)"
                )
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

import numpy as np  # noqa: E402  (guaranteed available in the base env)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def pick_platform():
    """Return the fastest available OpenMM Platform, falling back to CPU.

    Tries CUDA, then OpenCL, then CPU. Any platform that errors on
    instantiation is skipped."""
    for name in ("CUDA", "OpenCL", "CPU"):
        try:
            plat = mm.Platform.getPlatformByName(name)
            return plat, name
        except Exception:
            continue
    # getPlatform(0) always exists as a last resort.
    plat = mm.Platform.getPlatform(0)
    return plat, plat.getName()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Short molecular dynamics of a protein with OpenMM."
    )
    parser.add_argument("--pdb", required=True, help="Protein structure (.pdb)")
    parser.add_argument(
        "--ff",
        nargs="+",
        default=["amber14-all.xml", "amber14/tip3pfb.xml"],
        help="Force-field XML files (space-separated; default amber14-all + tip3pfb)",
    )
    parser.add_argument(
        "--solvent",
        choices=["implicit", "explicit"],
        default="implicit",
        help="Solvent model (default implicit GBn2 = fast)",
    )
    parser.add_argument("--steps", type=int, default=50000,
                        help="Production steps (default 50000 ~= 100 ps at 2 fs)")
    parser.add_argument("--equil-steps", dest="equil_steps", type=int, default=5000,
                        help="Equilibration steps (default 5000)")
    parser.add_argument("--temperature", type=float, default=300.0,
                        help="Temperature in Kelvin (default 300)")
    parser.add_argument("--dt-fs", dest="dt_fs", type=float, default=2.0,
                        help="Integration timestep in fs (default 2.0)")
    parser.add_argument("--report-interval", dest="report_interval", type=int, default=1000,
                        help="Steps between trajectory/log frames (default 1000)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    parser.add_argument("--keep-water", dest="keep_water", action="store_true",
                        help="Keep crystallographic water (default: removed)")
    parser.add_argument("--keep-hetero", dest="keep_hetero", action="store_true",
                        help="Keep heterogens/ligands (default: removed; note: unparametrized "
                             "ligands will fail force-field matching)")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()

    pdb_path = Path(args.pdb)
    if not pdb_path.exists():
        print(json.dumps({"error": f"pdb not found: {pdb_path}"}))
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    # --- 1. PDBFixer: repair the structure --------------------------------
    try:
        fixer = PDBFixer(filename=str(pdb_path))
        fixer.findMissingResidues()
        # Drop heterogens (keep or discard water per flag).
        if not args.keep_hetero:
            fixer.removeHeterogens(keepWater=args.keep_water)
        fixer.findNonstandardResidues()
        fixer.replaceNonstandardResidues()
        fixer.findMissingAtoms()
        fixer.addMissingAtoms()
        fixer.addMissingHydrogens(7.0)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"PDBFixer could not parse/repair the structure: {exc}"}))
        sys.exit(1)

    # --- 2. Build the System ----------------------------------------------
    temperature = args.temperature * unit.kelvin
    dt = args.dt_fs * unit.femtoseconds

    try:
        modeller = app.Modeller(fixer.topology, fixer.positions)

        if args.solvent == "implicit":
            # Add an implicit-solvent XML so amber14 gets GB parameters.
            ff_files = list(args.ff) + ["implicit/gbn2.xml"]
            forcefield = app.ForceField(*ff_files)
            system = forcefield.createSystem(
                modeller.topology,
                nonbondedMethod=app.NoCutoff,
                constraints=app.HBonds,
            )
        else:
            forcefield = app.ForceField(*args.ff)
            # Solvate in a TIP3P box with 1 nm padding.
            modeller.addSolvent(forcefield, model="tip3p", padding=1.0 * unit.nanometer)
            system = forcefield.createSystem(
                modeller.topology,
                nonbondedMethod=app.PME,
                nonbondedCutoff=1.0 * unit.nanometer,
                constraints=app.HBonds,
            )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "error": f"System build failed (force-field mismatch or unparametrized "
                     f"residue/ligand): {exc}"}))
        sys.exit(1)

    # --- 3. Integrator + platform -----------------------------------------
    integrator = mm.LangevinMiddleIntegrator(temperature, 1.0 / unit.picosecond, dt)
    integrator.setRandomNumberSeed(args.seed)
    platform, platform_name = pick_platform()

    try:
        simulation = app.Simulation(modeller.topology, system, integrator, platform)
    except Exception:
        # Some platforms reject unsupported properties; retry on CPU.
        platform = mm.Platform.getPlatformByName("CPU")
        platform_name = "CPU"
        simulation = app.Simulation(modeller.topology, system, integrator, platform)
    simulation.context.setPositions(modeller.positions)

    # --- 4. Minimize + save reference -------------------------------------
    simulation.minimizeEnergy()
    minimized_pdb = outdir / "minimized.pdb"
    min_state = simulation.context.getState(getPositions=True)
    with minimized_pdb.open("w") as fh:
        app.PDBFile.writeFile(simulation.topology, min_state.getPositions(), fh)

    n_atoms = simulation.topology.getNumAtoms()

    # --- 5. Equilibration --------------------------------------------------
    simulation.context.setVelocitiesToTemperature(temperature, args.seed)
    if args.equil_steps > 0:
        simulation.step(args.equil_steps)

    # --- 6. Production run with reporters ----------------------------------
    traj_dcd = outdir / "trajectory.dcd"
    energy_csv = outdir / "energy_log.csv"
    simulation.reporters.append(
        app.DCDReporter(str(traj_dcd), args.report_interval)
    )
    simulation.reporters.append(
        app.StateDataReporter(
            str(energy_csv),
            args.report_interval,
            step=True,
            potentialEnergy=True,
            temperature=True,
            elapsedTime=True,
        )
    )
    simulation.step(args.steps)

    # Flush reporters by dropping references.
    simulation.reporters.clear()

    # --- 7. Backbone RMSD vs the minimized frame --------------------------
    final_rmsd = None
    mean_rmsd = None
    rmsd_csv = outdir / "rmsd.csv"
    rmsd_png = outdir / "rmsd.png"
    try:
        ref = md.load(str(minimized_pdb))
        traj = md.load(str(traj_dcd), top=str(minimized_pdb))
        backbone = traj.topology.select("backbone")
        if backbone.size == 0:
            backbone = traj.topology.select("name CA")
        traj.superpose(ref, atom_indices=backbone)
        rmsd = md.rmsd(traj, ref, atom_indices=backbone)  # nm, one value per frame

        ps_per_frame = args.report_interval * args.dt_fs / 1000.0  # fs -> ps
        times_ps = np.arange(1, len(rmsd) + 1) * ps_per_frame

        with rmsd_csv.open("w", encoding="utf-8") as fh:
            fh.write("frame,time_ps,backbone_rmsd_nm\n")
            for i, (t_ps, r) in enumerate(zip(times_ps, rmsd), 1):
                fh.write(f"{i},{t_ps:.3f},{r:.5f}\n")

        if len(rmsd):
            final_rmsd = float(rmsd[-1])
            mean_rmsd = float(np.mean(rmsd))
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.plot(times_ps, rmsd, color="#2b6cb0")
            ax.set_xlabel("Time (ps)")
            ax.set_ylabel("Backbone RMSD (nm)")
            ax.set_title("Backbone RMSD vs minimized frame")
            fig.tight_layout()
            fig.savefig(rmsd_png, dpi=150)
            plt.close(fig)
    except Exception as exc:  # noqa: BLE001 - trajectory produced, RMSD is a bonus
        print(f"[warn] RMSD analysis failed: {exc}", file=sys.stderr)

    # --- 8. Summary --------------------------------------------------------
    wall = round(time.time() - t0, 1)
    summary = {
        "input_pdb": str(pdb_path),
        "n_atoms": int(n_atoms),
        "solvent": args.solvent,
        "forcefield": list(args.ff),
        "steps": args.steps,
        "equil_steps": args.equil_steps,
        "dt_fs": args.dt_fs,
        "temperature_K": args.temperature,
        "report_interval": args.report_interval,
        "platform": platform_name,
        "final_backbone_rmsd_nm": None if final_rmsd is None else round(final_rmsd, 4),
        "mean_backbone_rmsd_nm": None if mean_rmsd is None else round(mean_rmsd, 4),
        "wall_time_sec": wall,
        "outputs": [
            "minimized.pdb", "trajectory.dcd", "energy_log.csv",
            "rmsd.csv", "rmsd.png", "md_summary.json",
        ],
    }
    (outdir / "md_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- short summary to stdout ------------------------------------------
    print("MD_SKILL_OK " + json.dumps(
        {"n_atoms": int(n_atoms), "steps": args.steps, "platform": platform_name,
         "wall_time_sec": wall}, ensure_ascii=False))
    print(f"Atoms: {n_atoms} | solvent: {args.solvent} | platform: {platform_name} | "
          f"{args.steps} steps in {wall}s")
    if mean_rmsd is not None:
        print(f"Backbone RMSD: mean {mean_rmsd:.3f} nm, final {final_rmsd:.3f} nm  -> {rmsd_png}")
    print(f"Trajectory: {traj_dcd}")


if __name__ == "__main__":
    main()
