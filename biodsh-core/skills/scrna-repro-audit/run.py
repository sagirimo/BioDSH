"""Reproducibility audit over a completed BioDSH run bundle.

输入是某次运行的 result.json。审计核对该 bundle 的输入、环境、命令、输出和
结论是否互相一致，输出机器可读的审计报告。审计只读取文件，不修改 bundle，
不重跑分析，也不评估生物学结论本身。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BUNDLE_FILES = [
    "input.json",
    "env.json",
    "command.sh",
    "outputs.json",
    "result.json",
    "stdout.log",
    "stderr.log",
]

SUCCESS_STATUSES = {"passed", "executed", "ungraded"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, passed: bool | None, detail: str) -> dict:
    status = "not_applicable" if passed is None else ("pass" if passed else "fail")
    return {"check": name, "status": status, "detail": detail}


def audit_bundle_complete(run_dir: Path) -> dict:
    missing = [name for name in BUNDLE_FILES if not (run_dir / name).is_file()]
    return check(
        "bundle_complete",
        not missing,
        "all bundle files present" if not missing else f"missing: {', '.join(missing)}",
    )


def audit_input_consistency(input_meta: dict) -> dict:
    recorded_path = input_meta.get("input_path")
    recorded_hash = input_meta.get("input_sha256")
    if recorded_path is None:
        return check("input_consistency", None, "run declared no input file")
    input_path = Path(recorded_path)
    if not input_path.is_file():
        return check("input_consistency", False, f"input file missing: {recorded_path}")
    current = sha256(input_path)
    return check(
        "input_consistency",
        current == recorded_hash,
        "input file hash matches the pre-execution snapshot"
        if current == recorded_hash
        else "input file no longer matches the recorded sha256",
    )


def audit_command_consistency(run_dir: Path, input_meta: dict) -> dict:
    command_path = run_dir / "command.sh"
    if not command_path.is_file():
        return check("command_consistency", False, "command.sh missing")
    command = command_path.read_text(encoding="utf-8")
    problems = []
    seed = input_meta.get("seed")
    if seed is not None and f"--seed {seed}" not in command:
        problems.append(f"seed {seed} not in command")
    recorded_path = input_meta.get("input_path")
    if recorded_path is not None and recorded_path not in command:
        problems.append("input path not in command")
    if str(run_dir) not in command:
        problems.append("outdir not in command")
    return check(
        "command_consistency",
        not problems,
        "command records the same seed, input and outdir" if not problems else "; ".join(problems),
    )


def audit_output_integrity(run_dir: Path, outputs_meta: dict) -> dict:
    if not outputs_meta:
        return check("output_integrity", None, "no outputs recorded")
    mismatched = []
    for name, item in outputs_meta.items():
        path = run_dir / name
        if not path.is_file():
            mismatched.append(f"{name} (missing)")
        elif sha256(path) != item.get("sha256"):
            mismatched.append(f"{name} (hash changed)")
    return check(
        "output_integrity",
        not mismatched,
        f"all {len(outputs_meta)} outputs match their recorded sha256"
        if not mismatched
        else "; ".join(mismatched),
    )


def audit_result_consistency(result: dict, outputs_meta: dict) -> dict:
    recorded = result.get("evidence", {}).get("output_sha256", {})
    from_outputs = {name: item.get("sha256") for name, item in outputs_meta.items()}
    if recorded != from_outputs:
        return check(
            "result_consistency", False, "result.json output hashes differ from outputs.json"
        )
    status = result.get("status")
    scores = result.get("scores", {})
    if status in SUCCESS_STATUSES and scores.get("executed") != 1.0:
        return check("result_consistency", False, f"status {status} but executed != 1.0")
    if status == "passed" and scores.get("artifact_contract_validity") != 1.0:
        return check(
            "result_consistency", False, "status passed but artifact_contract_validity != 1.0"
        )
    return check("result_consistency", True, "result.json agrees with outputs.json and its own scores")


def audit_declared_outputs(result: dict, outputs_meta: dict) -> dict:
    declared = result.get("evidence", {}).get("declared_outputs", [])
    if result.get("status") not in SUCCESS_STATUSES:
        return check("declared_outputs_present", None, "run did not succeed; completeness not asserted")
    missing = [name for name in declared if name not in outputs_meta]
    return check(
        "declared_outputs_present",
        not missing,
        f"all {len(declared)} declared outputs recorded" if not missing else f"missing: {', '.join(missing)}",
    )


def audit_grader_evidence(result: dict) -> dict:
    grader = result.get("evidence", {}).get("artifact_grader")
    if grader is None:
        return check("grader_evidence", None, "no artifact grader evidence recorded")
    problems = []
    if grader.get("passed") is True:
        if grader.get("returncode") != 0:
            problems.append("grader passed but returncode != 0")
        passed_checks = grader.get("passed_checks")
        total_checks = grader.get("total_checks")
        if passed_checks is not None and total_checks is not None and passed_checks != total_checks:
            problems.append("grader passed but passed_checks != total_checks")
        scores = result.get("scores", {})
        other_axis_failed = any(
            scores.get(axis) == 0.0
            for axis in ("executed", "input_integrity", "benchmark_grader_integrity", "offline")
        )
        if result.get("status") == "failed" and not other_axis_failed:
            problems.append("grader passed but run status is failed with no failing axis recorded")
    return check(
        "grader_evidence",
        not problems,
        "grader evidence internally consistent" if not problems else "; ".join(problems),
    )


def audit_offline_evidence(result: dict, env_meta: dict) -> dict:
    observation = result.get("evidence", {}).get("offline_observation")
    offline_score = result.get("scores", {}).get("offline")
    if observation is None:
        return check(
            "offline_evidence",
            offline_score is None,
            "no observation recorded and offline axis unscored"
            if offline_score is None
            else "offline scored without any recorded observation",
        )
    problems = []
    if offline_score == 1.0 and observation.get("isolation_observed") is not True:
        problems.append("offline scored 1.0 without isolation_observed")
    if env_meta.get("network_isolation") != "netns":
        problems.append("observation recorded but env.json lacks network_isolation=netns")
    return check(
        "offline_evidence",
        not problems,
        "offline score backed by a recorded namespace observation" if not problems else "; ".join(problems),
    )


def run_audit(target_result: Path) -> dict:
    run_dir = target_result.parent
    checks = [audit_bundle_complete(run_dir)]
    result = load_json(target_result) if target_result.is_file() else {}
    input_meta = load_json(run_dir / "input.json") if (run_dir / "input.json").is_file() else {}
    outputs_meta = load_json(run_dir / "outputs.json") if (run_dir / "outputs.json").is_file() else {}
    env_meta = load_json(run_dir / "env.json") if (run_dir / "env.json").is_file() else {}

    checks.append(audit_input_consistency(input_meta))
    checks.append(audit_command_consistency(run_dir, input_meta))
    checks.append(audit_output_integrity(run_dir, outputs_meta))
    checks.append(audit_result_consistency(result, outputs_meta))
    checks.append(audit_declared_outputs(result, outputs_meta))
    checks.append(audit_grader_evidence(result))
    checks.append(audit_offline_evidence(result, env_meta))

    failed = [item["check"] for item in checks if item["status"] == "fail"]
    evaluated = [item for item in checks if item["status"] != "not_applicable"]
    return {
        "schema_version": "1.0",
        "audited_run_id": run_dir.name,
        "audited_skill_id": result.get("skill_id"),
        "audited_status": result.get("status"),
        "checks": checks,
        "evaluated_checks": len(evaluated),
        "failed_checks": failed,
        "audit_passed": not failed,
        "scope": "bundle_internal_consistency",
        "biological_validity": "not_evaluated",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="被审计运行的 result.json 路径")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    report = run_audit(Path(args.input).resolve())

    (outdir / "repro_audit_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = ["check,status,detail"]
    for item in report["checks"]:
        detail = item["detail"].replace('"', "'")
        lines.append(f'{item["check"]},{item["status"]},"{detail}"')
    (outdir / "repro_audit_summary.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not report["audit_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
