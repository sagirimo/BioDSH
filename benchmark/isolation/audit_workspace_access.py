"""Audit agent tool calls for access outside the task workspace (BioDSH sessions, Codex and Claude Code transcripts).

Every run must stay inside its workspace: the agents' sandboxes restrict writes, not reads, so a workspace placed next to
earlier runs, grades or curator references can leak answers (2026-10-19 loop round 5: 4/15 BioDSH sessions listed the
parent directories and read earlier runs' interpretation_claims.json). This script lists, per task, every tool call that
names an absolute path outside the workspace or walks up out of it. Flags are for review: a listed call is not proof of
use, an unlisted run is clean under these rules. Exit status 1 when anything is flagged.

BioDSH: agent.json `sid` is looked up under the dsh homes given with --sessions (<home>/sessions/*/<sid>/, or one level below DIR); the workspace is
the session's cwd. Codex/Claude: transcript.jsonl in the task directory; the workspace is the command's cwd as reported.
Usage: audit_workspace_access.py [--sessions DIR]... RUN_DIR ...
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

ABS = re.compile(r'(?:(?<![\w])[A-Za-z]:\\(?:[\w .$~-]+\\)+[^\s"\'|;,)<>]*|(?<![\w])[A-Za-z]:\\(?=["\'\s])|/(?:mnt|home|root|Users|tmp|opt|srv)/[^\s"\'|;,)<>]*)')
# walking up from the workspace: '../..', or '..' not followed by a file that lives in the workspace root
UP = re.compile(r'(?<![\w.\]$])(?:\.\.[\\/]\.\.|\.\.(?![\\/](?:inputs|submission|prompt\.md|TABLE_CONTRACT\.json|CLAIMS\.json|analysis\.py)\b)(?=[\\/\s"\';|)]|$))')
CD_UP = re.compile(r'(?:^|[;&|"]\s*|\n)\s*(?:cd|Set-Location|Push-Location)\s+\.\.(?=\s*(?:$|[;&|\n]))')
ALLOW = ('/bench/env', '\\bench\\env', '/usr/', '/bin/', '/dev/null', '\\Desktop\\BioDSH\\', '\\Windows\\', '\\Program Files')


def zstd_lines(path):
    """Records of one session file; a truncated last record (session still flushing) is skipped."""
    import zstandard
    with open(path, 'rb') as f:
        lines = zstandard.ZstdDecompressor().stream_reader(f).read().decode('utf-8', 'replace').splitlines()
    out = []
    for line in lines:
        try:
            json.loads(line)
            out.append(line)
        except ValueError:
            pass
    return out


def session_index(roots):
    """sid -> session file, for the dsh homes under each root (sessions/<workspace>/<sid>/session.v*.jsonl.zstd)."""
    return {Path(f).parent.name: f for r in roots for pat in ('sessions', '*/sessions')
            for f in glob.glob(f'{r}/{pat}/*/session-*/session.v*.jsonl.zstd')}


def biodsh_calls(task_dir, index):
    sid = json.loads((task_dir / 'agent.json').read_text('utf-8')).get('sid')
    if sid not in index:
        return None, []
    ws, calls = None, []
    for line in zstd_lines(index[sid]):
        e = json.loads(line)
        if e.get('type') == 'session':
            ws = e.get('cwd') or (e.get('data') or {}).get('cwd')
        elif e.get('type') == 'tool/call':
            d = e['data']
            calls.append((d.get('step'), d.get('name'), d.get('arguments') or ''))
    return ws, calls


def cli_calls(task_dir):
    ws, calls = None, []
    t = task_dir / 'transcript.jsonl'
    if not t.exists():
        return None, []
    for line in t.read_text('utf-8', 'replace').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get('item') or {}
        if item.get('type') == 'command_execution' and e.get('type') == 'item.completed':
            calls.append((len(calls) + 1, 'shell', item.get('command') or ''))
        if e.get('type') == 'system' and e.get('cwd'):
            ws = e['cwd']
        for b in ((e.get('message') or {}).get('content') or []) if e.get('type') == 'assistant' else []:
            if b.get('type') == 'tool_use':
                calls.append((len(calls) + 1, b.get('name'), json.dumps(b.get('input') or {}, ensure_ascii=False)))
    return ws, calls


WRITERS = {'write', 'edit', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'apply_patch'}


def flags(ws, name, text):
    try:
        args = json.loads(text)
        # file-writing tools: only the target path matters; the body is code whose own reads happen in the workspace replay
        if name in WRITERS and isinstance(args, dict):
            args = {k: v for k, v in args.items() if k in ('file_path', 'path', 'notebook_path')}
        text = json.dumps(args, ensure_ascii=False)
    except (ValueError, TypeError):
        pass
    text = text.replace('\\\\', '\\').replace('\\n', '\n')
    variants = {ws, ws.replace('\\', '/'), ws.rstrip('\\/')} if ws else set()
    for v in sorted(variants, key=len, reverse=True):
        text = text.replace(v, '<WS>')
    out = [p for p in ABS.findall(text) if not any(a in p for a in ALLOW)]
    stripped = CD_UP.sub(' ', text)
    out += [f'..{m.group(0)[2:]}' for m in UP.finditer(stripped)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sessions', action='append', default=[], help='dsh home directory holding BioDSH sessions (repeatable)')
    ap.add_argument('runs', nargs='+')
    a = ap.parse_args()
    flagged, index = 0, session_index(a.sessions)
    for run in a.runs:
        tasks = sorted(p for p in Path(run).iterdir() if (p / 'agent.json').exists())
        clean, missing = 0, []
        print(f'== {run} ({len(tasks)} tasks)')
        for t in tasks:
            ws, calls = cli_calls(t) if (t / 'transcript.jsonl').exists() else biodsh_calls(t, index)
            if not calls:
                missing.append(t.name)
                continue
            hits = [(s, n, f) for s, n, txt in calls for f in [flags(ws, n, txt)] if f]
            if not hits:
                clean += 1
                continue
            flagged += 1
            print(f'  {t.name.replace("biodsh-candidate-", "")}: {len(hits)} call(s)')
            for s, n, f in hits[:6]:
                print(f'      step {s} {n}: {", ".join(sorted(set(x[:120] for x in f)))}')
        print(f'  clean {clean}/{len(tasks)}' + (f'; no transcript for {len(missing)}: {", ".join(missing)}' if missing else ''))
    sys.exit(1 if flagged else 0)


if __name__ == '__main__':
    main()
