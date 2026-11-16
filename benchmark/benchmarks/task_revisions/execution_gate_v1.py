"""Shared evaluator-private execution gate. Receipts are not caller authentication.

Only a trusted controller may provide receipt paths/digests. Default limits are
accepted here; this module never authorizes a task-specific resource exception.
"""
import hashlib
import math
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def binding(submission, base, revision, read):
    root = revision.parents[2]
    card = read(base/'task_metadata.json')
    files = [Path(__file__), revision/'grade.py', revision/'grade_delivered.py',
             root/'scripts/benchmark_namespace_executor.py',
             root/'benchmarks/grader_patches/json_contract_v1/grade_task.py']
    return dict(submission_binding=submission,
                inputs={r['file']: digest(base/'task/inputs'/r['file']) for r in card['input_files']},
                evaluator={p.relative_to(root).as_posix(): digest(p) for p in files})


def validate(record, expected):
    if not isinstance(record, dict) or record.get('binding') != expected:
        raise ValueError('Stale execution binding')
    if record.get('kind') not in ('actual_execution', 'test_fixture') or record.get('evaluator_owned') is not True:
        raise ValueError('Evaluator-owned execution record required')
    if record.get('status') != 'completed_isolated_code_replay':
        raise ValueError('Completed code replay required')
    terminal = record.get('terminal')
    if not isinstance(terminal, dict):
        raise ValueError('Missing terminal evidence')
    for field in ('process_tree_terminal', 'inputs_unchanged', 'fresh_outputs', 'submitted_code_replayed',
                  'inputs_readonly', 'network_disabled', 'gold_unmounted', 'resource_limits_enforced'):
        if terminal.get(field) is not True:
            raise ValueError('Missing execution condition: '+field)
    for field in ('timed_out', 'cancelled', 'output_limit_exceeded'):
        if terminal.get(field) is not False:
            raise ValueError('Abnormal execution: '+field)
    if type(terminal.get('exit_code')) is not int or terminal['exit_code'] != 0:
        raise ValueError('Replay did not exit successfully')
    limits = record.get('resource_limits')
    expected_limits = dict(address_space_bytes=1024**3, cpu_seconds=15, file_bytes=8*1024**2)
    if record.get('resource_profile') != 'default' or limits != expected_limits or any(type(v) is not int for v in limits.values()):
        raise ValueError('Unapproved execution resource profile')
    wall = record.get('wall_limit_seconds')
    if type(wall) not in (int, float) or not math.isfinite(wall) or not 0 < wall <= 60:
        raise ValueError('Invalid wall limit')
    if not isinstance(record.get('runner_id'), str) or not record['runner_id'].strip():
        raise ValueError('Missing runner identity')
    files = record.get('evidence_files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Retained private execution evidence required')
    for name, sha in files.items():
        if not isinstance(name, str) or Path(name).name != name or any(c in name for c in ('/', '\\', ':')) or name in ('.', '..') or not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('Invalid execution evidence descriptor')
    return dict(execution_verified=record['kind'] == 'actual_execution', test_only=record['kind'] == 'test_fixture')


def read_private(path, sha, outputs, expected, read):
    if path is None or not isinstance(sha, str) or len(sha) != 64:
        raise ValueError('Both private execution path and SHA256 required')
    path = Path(path).resolve()
    outputs = [Path(p).resolve() for p in outputs]
    def submitted(p):
        return any(p == out or p.is_relative_to(out) for out in outputs)
    if submitted(path) or digest(path) != sha:
        raise ValueError('Execution record must be evaluator-private and unchanged')
    record = read(path)
    result = validate(record, expected)
    for name, expected_sha in record['evidence_files'].items():
        log = (path.parent/name).resolve()
        if not log.is_relative_to(path.parent) or submitted(log) or digest(log) != expected_sha:
            raise ValueError('Private execution evidence missing, escaped, or changed')
    return result


def finalize(result):
    result['passed'] = all(result.get(k) is True for k in
                           ('artifact_pass', 'evidence_reference_pass', 'semantic_verified', 'execution_verified'))
    if result['passed']:
        result['status'] = 'passed'
    elif result.get('status') in ('passed', 'needs_semantic_review', 'needs_execution_and_semantic_review'):
        result['status'] = ('needs_execution' if result.get('semantic_verified') is True else
                            'needs_semantic_review' if result.get('execution_verified') is True else
                            'needs_execution_and_semantic_review')
    return result
