"""Shared grader for lean multistep tasks (benchmarks/lean_tasks/<task_id>).

Layout: public/{prompt.md, TABLE_CONTRACT.json, CLAIMS.json, inputs/*}, private/{ANSWER_KEY_PRIVATE.json,
expected/*.csv}, task_metadata.json. A submission directory holds the contract tables, analysis.py and
interpretation_claims.json. Passing requires: every contract table equal by key (typed, per-column
tolerance), every structured claim correct, and an evaluator-owned code-replay receipt bound to the
submission, inputs and this evaluator.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLAIMS_FILE = 'interpretation_claims.json'


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


CLAIMS = _module('lean_structured_claims', ROOT / 'benchmarks/grader_patches/structured_interpretation_v1/structured_claims.py')
GATE = _module('lean_execution_gate', ROOT / 'benchmarks/task_revisions/execution_gate_v1.py')
read = CLAIMS.read_json
DEFAULT_LIMITS = dict(address_space_bytes=1024**3, cpu_seconds=15, file_bytes=8 * 1024**2)


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load_table(path, spec):
    with open(path, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        if r.fieldnames is None or len(r.fieldnames) != len(set(r.fieldnames)) or set(r.fieldnames) != set(spec['columns']):
            raise ValueError(f'{path.name}: header must be exactly {spec["columns"]}')
        rows = {}
        for row in r:
            k = tuple(row[c].strip() for c in spec['key'])
            if k in rows:
                raise ValueError(f'{path.name}: duplicate key {k}')
            rows[k] = row
    return rows


def cell_ok(kind, a, b, tol):
    a, b = a.strip(), b.strip()
    if a in ('', 'NA') or b in ('', 'NA'):
        return (a in ('', 'NA')) == (b in ('', 'NA'))
    if kind == 'text':
        return a == b
    try:
        x, y = float(a), float(b)
    except ValueError:
        return False
    if not (math.isfinite(x) and math.isfinite(y)):
        return False
    if kind == 'int':
        return x == y
    return math.isclose(x, y, rel_tol=tol[0], abs_tol=tol[1])


def compare_tables(task, out):
    contract = read(task / 'public/TABLE_CONTRACT.json')
    report = {}
    for name, spec in contract['tables'].items():
        p = out / name
        if not p.is_file():
            report[name] = 'missing'
            continue
        try:
            got, exp = load_table(p, spec), load_table(task / 'private/expected' / name, spec)
        except (OSError, ValueError, KeyError) as e:
            report[name] = f'invalid: {e}'
            continue
        if set(got) != set(exp):
            report[name] = f'key set differs: missing {len(set(exp) - set(got))}, extra {len(set(got) - set(exp))}'
            continue
        bad = []
        for k, er in exp.items():
            for c in spec['columns']:
                kind = spec['types'].get(c, 'text')
                if not cell_ok(kind, got[k][c], er[c], spec.get('tolerance', {}).get(c, [0, 0])):
                    bad.append((k, c))
                    if len(bad) >= 5:
                        break
            if len(bad) >= 5:
                break
        report[name] = 'pass' if not bad else f'mismatch at {bad}'
    return all(v == 'pass' for v in report.values()), report


def binding(task, out):
    meta = read(task / 'task_metadata.json')
    files = sorted(p for p in Path(out).rglob('*') if p.is_file())
    if any(p.is_symlink() for p in Path(out).rglob('*')):
        raise ValueError('Symlinks are not allowed in submissions')
    evaluator = [HERE / 'lean_grade.py', ROOT / 'benchmarks/grader_patches/structured_interpretation_v1/structured_claims.py',
                 ROOT / 'benchmarks/task_revisions/execution_gate_v1.py', task / 'private/ANSWER_KEY_PRIVATE.json',
                 task / 'public/TABLE_CONTRACT.json', task / 'public/CLAIMS.json', task / 'public/prompt.md']
    evaluator += sorted((task / 'private/expected').glob('*'))
    return dict(task_id=meta['task_id'], revision=meta['revision'],
                submission={p.relative_to(out).as_posix(): digest(p) for p in files},
                inputs={p.name: digest(p) for p in sorted((task / 'public/inputs').glob('*'))},
                evaluator={p.relative_to(ROOT).as_posix(): digest(p) for p in evaluator})


def validate_receipt(task, record, expected):
    """Accept the default profile, or exactly the task's declared profile (user-approved rule)."""
    meta = read(task / 'task_metadata.json')
    prof = meta.get('resource_profile', 'default')
    if isinstance(record, dict) and prof != 'default' and record.get('resource_profile') == prof:
        if record.get('resource_limits') != meta['resource_limits']:
            raise ValueError('Wrong approved task-specific limits')
        wall = record.get('wall_limit_seconds')
        if type(wall) not in (int, float) or not 0 < wall <= meta['wall_seconds']:
            raise ValueError('Invalid task-specific wall limit')
        record = dict(record, resource_profile='default', resource_limits=DEFAULT_LIMITS, wall_limit_seconds=60)
    return GATE.validate(record, expected)


def grade(task, out, execution_receipt=None, execution_sha256=None):
    task, out = Path(task).resolve(), Path(out).resolve()
    result = dict(passed=False, task_id=read(task / 'task_metadata.json')['task_id'], artifact_pass=False,
                  evidence_reference_pass=False, semantic_verified=False, execution_verified=False, llm_review=False)
    ok, report = compare_tables(task, out)
    result.update(artifact_pass=ok, tables=report)
    if not ok:
        result['status'] = 'failed_artifacts'
        return result
    try:
        spec = read(task / 'public/CLAIMS.json')
        claims = CLAIMS.grade(out, spec, read(task / 'private/ANSWER_KEY_PRIVATE.json'), CLAIMS_FILE)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        result.update(status='failed_interpretation_schema', issues=[str(e)])
        return result
    numeric = [c['id'] for c in spec['claims'] if c['type'] == 'number']
    result.update(evidence_reference_pass=all(claims['claim_results'][i] == 'pass' for i in numeric),
                  semantic_verified=claims['semantic_verified'], claim_results=claims['claim_results'])
    if not claims['semantic_verified']:
        result['status'] = 'failed_semantics'
        return result
    result['status'] = 'needs_execution_and_semantic_review'
    if execution_receipt is not None or execution_sha256 is not None:
        try:
            path, sha = Path(execution_receipt).resolve(), execution_sha256
            if path.is_relative_to(out) or not isinstance(sha, str) or digest(path) != sha:
                raise ValueError('Execution record must be evaluator-private and unchanged')
            record = read(path)
            ex = validate_receipt(task, record, binding(task, out))
            for name, s in record['evidence_files'].items():
                log = (path.parent / name).resolve()
                if not log.is_relative_to(path.parent) or digest(log) != s:
                    raise ValueError('Private execution evidence missing or changed')
            result['execution_verified'] = ex['execution_verified']
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            result.update(status='invalid_execution', issues=[str(e)])
            return result
    return GATE.finalize(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--task', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execution-receipt', type=Path)
    p.add_argument('--execution-sha256')
    a = p.parse_args()
    try:
        r = grade(a.task, a.output, a.execution_receipt, a.execution_sha256)
    except (OSError, ValueError, KeyError, TypeError) as e:
        r = dict(passed=False, status='evaluator_error', issues=[str(e)])
    print(json.dumps(r, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0 if r['passed'] else 1)
