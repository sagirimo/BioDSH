"""Grade one agent submission for a lean task: isolated evaluator-owned replay of the submitted analysis.py, then lean_grade.

The agent's own output files are never trusted for the official grade; tables and claims come from the replay.
A secondary 'self_reported' grade on the agent's own submission directory (no receipt) is kept for the
final-answer-only vs execution-evidence comparison. Format-only failures are labelled separately.
Usage: grade_agent_lean.py <benchmarks/lean_tasks/<id>> <submission dir with analysis.py> <run dir (must not exist)>
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SCIENCE = ROOT / '.tools/benchmark-linux-science-20261013'
# BIODSH_SCIENCE_DIR: the same replay environment on a fast local filesystem. Under WSL the repository is on /mnt/c,
# where importing numpy/pandas/scipy inside the sandbox takes ~14 s of wall time (CPU ~1 s), so 15 s wall-limited
# tasks failed at random (2026-10-20). The copy must have the frozen tree hash; anything else is refused.
SCIENCE_SHA256 = 'f13cfef6073e987c5909e8965f5967f243899f17df681c935847761b3b7e1120'
if os.environ.get('BIODSH_SCIENCE_DIR'):
    _alt = Path(os.environ['BIODSH_SCIENCE_DIR']).resolve(strict=True)
    _h = hashlib.sha256()
    for _p in sorted(x for x in _alt.rglob('*') if x.is_file() and not any(s in x.parts for s in ('__pycache__', 'selfcheck', 'selfcheck_runs'))):
        with open(_p, 'rb') as _f:
            _h.update(_p.relative_to(_alt).as_posix().encode() + b'\0' + hashlib.file_digest(_f, 'sha256').hexdigest().encode() + b'\n')
    if _h.hexdigest() != SCIENCE_SHA256:
        sys.exit(f'BIODSH_SCIENCE_DIR {_alt} does not match the frozen replay environment hash')
    SCIENCE = _alt
sys.path.insert(0, str(ROOT / 'scripts'))
GRADER = ROOT / 'benchmarks/grader_patches/lean_task_v1/lean_grade.py'
FORMAT_STATUSES = ('failed_interpretation_schema',)


def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
def save(p, v): Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf-8')


def lean_grade(task, out, receipt=None, sha=None):
    cmd = [sys.executable, '-I', '-S', '-B', str(GRADER), '--task', str(task), '--output', str(out)]
    if receipt:
        cmd += ['--execution-receipt', str(receipt), '--execution-sha256', sha]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return dict(passed=False, status='grader_error', issues=[(p.stderr or p.stdout)[-1500:]])


def main():
    assert sys.platform == 'linux'
    from benchmark_namespace_executor import run, resource_limits
    import importlib.util
    spec = importlib.util.spec_from_file_location('lean_grade', GRADER)
    L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
    task, sub, RUN = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    assert not RUN.exists(), 'Never repeat a possibly completed grading run'
    RUN.mkdir(parents=True)
    meta = read(task / 'task_metadata.json')
    res = dict(task_id=meta['task_id'], submission=str(sub))
    code_path = sub / 'analysis.py'
    if not code_path.is_file():
        res.update(passed=False, status='no_analysis_py', failure_kind='format')
        save(RUN / 'AGENT_GRADE.json', res); print(json.dumps(res, ensure_ascii=False)); return
    # Secondary: the agent's own files, final-answer-only view (no execution evidence).
    res['self_reported'] = {k: v for k, v in lean_grade(task, sub).items() if k in ('status', 'artifact_pass', 'semantic_verified', 'claim_results', 'issues')}
    public = RUN / 'public'
    (public / 'task').mkdir(parents=True)
    shutil.copytree(task / 'public/inputs', public / 'task/inputs')
    # The executor checks a task-bound resource profile against the task card in the sandbox; give it the id only.
    (public / 'task_metadata.json').write_text(json.dumps({'task_id': meta['task_id']}), 'utf-8')
    code = code_path.read_bytes()
    (public / 'submitted_analysis.py').write_bytes(code)
    output, state = RUN / 'worker_output', RUN / 'state'
    output.mkdir(); state.mkdir()
    profile, wall = meta.get('resource_profile', 'default'), meta.get('wall_seconds', 60)
    bootstrap = ("import sys,runpy;sys.path[:0]=['/opt/science'];sys.argv=['/work/task/submitted_analysis.py','--inputs','/work/task/task/inputs',"
                 "'--out','/work/output/result'];runpy.run_path(sys.argv[0],run_name='__main__')")
    ex = run(public, output, state, ['/usr/bin/python3', '-I', '-S', '-B', '-c', bootstrap], timeout=wall, science_dir=SCIENCE, resource_profile=profile)
    save(RUN / 'EXECUTION.json', ex)
    out = output / 'result'
    res['replay'] = {k: ex.get(k) for k in ('returncode', 'timed_out', 'cancelled', 'output_limit_exceeded')}
    if not (ex['process_terminal'] and ex['returncode'] == 0) or any(ex[k] for k in ('timed_out', 'cancelled', 'output_limit_exceeded')):
        res.update(passed=False, status='replay_failed', failure_kind='execution', replay_stderr_tail=(ex.get('stderr') or '')[-1500:])
        save(RUN / 'AGENT_GRADE.json', res); print(json.dumps(res, ensure_ascii=False)); return
    self_copy = (out / 'analysis.py').is_file() and (out / 'analysis.py').read_bytes() == code
    if not self_copy:  # format-only omission: the evaluator places the replayed code itself
        (out / 'analysis.py').write_bytes(code)
    res['analysis_self_copy'] = self_copy
    save(RUN / 'LAUNCH.json', read(state / 'launch.json'))
    save(RUN / 'CONTROLLER.json', dict(actor='agent_submission_replay', public_inputs_unchanged=True,
                                       controller_sha256=L.digest(Path(__file__)),
                                       namespace_executor_sha256=L.digest(ROOT / 'scripts/benchmark_namespace_executor.py')))
    terminal = {k: True for k in ('process_tree_terminal', 'inputs_unchanged', 'fresh_outputs', 'submitted_code_replayed',
                                  'inputs_readonly', 'network_disabled', 'gold_unmounted', 'resource_limits_enforced')}
    terminal.update(exit_code=0, timed_out=False, cancelled=False, output_limit_exceeded=False)
    receipt = dict(binding=L.binding(task, out), kind='actual_execution', evaluator_owned=True, status='completed_isolated_code_replay',
                   terminal=terminal, runner_id='benchmark_namespace_executor:agent_submission_replay', resource_profile=profile,
                   resource_limits=ex['resource_limits'], wall_limit_seconds=wall,
                   evidence_files={n: L.digest(RUN / n) for n in ('EXECUTION.json', 'LAUNCH.json', 'CONTROLLER.json')})
    rp = RUN / 'execution_receipt.json'
    save(rp, receipt)
    g = lean_grade(task, out, rp, L.digest(rp))
    save(RUN / 'GRADE.json', g)
    status = g.get('status')
    res.update(passed=bool(g.get('passed')), status=status, artifact_pass=g.get('artifact_pass'),
               semantic_verified=g.get('semantic_verified'), claim_results=g.get('claim_results'),
               failure_kind=None if g.get('passed') else ('format' if status in FORMAT_STATUSES else 'scientific'),
               failed_tables={t: r for t, r in (g.get('tables') or {}).items() if r != 'pass'})
    save(RUN / 'AGENT_GRADE.json', res)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
