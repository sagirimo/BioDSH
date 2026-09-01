#!/usr/bin/env python3
"""把示范实例里跑好的会话打包进 resources/demos：重命名标题（倒序，保证第一段在侧栏最上面）、
拷贝日志到 <demo>/.session/<sid>.jsonl.zstd、写 demo.json 的 sessions 列表。
用法：export_demo_sessions.py --port 13399 --demo-home <tmp/dsh-home-demo> --plan plan.json
plan.json: {"01-scrna-analysis": [{"id": "session-...", "title": "..."}, ...], ...}"""
import argparse, json, os, shutil, subprocess, sys, uuid
CURL = '/mnt/c/Windows/System32/curl.exe'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_CWD = 'C:\\Users\\MOLIEX-DESKTOP\\BioDSH\\demos\\'

def rpc(port, method, payload):
    body = json.dumps({'type': 'client-request', 'rpcId': str(uuid.uuid4()), 'method': method, 'payload': payload}, ensure_ascii=False)
    out = subprocess.run([CURL, '-s', '-m', '60', '-X', 'POST', f'http://127.0.0.1:{port}/api/{method}', '-H', 'Content-Type: application/json', '--data-binary', '@-'], input=body.encode('utf-8'), capture_output=True).stdout
    r = json.loads(out.decode('utf-8', 'replace')).get('result', {})
    if not r.get('ok'): raise RuntimeError(f'{method}: {r.get("error")}')
    return r.get('value')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--port', type=int, required=True); ap.add_argument('--demo-home', required=True); ap.add_argument('--plan', required=True)
    a = ap.parse_args(); plan = json.load(open(a.plan, encoding='utf-8'))
    for demo, sessions in plan.items():
        # 倒序重命名：rename 会追加事件、更新 updatedAt → 最后改的排最前
        for s in reversed(sessions):
            rpc(a.port, 'session.rename', {'sessionId': s['id'], 'title': s['title']})
        ddir = os.path.join(ROOT, 'resources', 'demos', demo)
        sdir = os.path.join(ddir, '.session'); shutil.rmtree(sdir, ignore_errors=True); os.makedirs(sdir)
        slug = f'--C-Users-MOLIEX-DESKTOP-BioDSH-demos-{demo}--'
        out = []
        for s in sessions:
            src = os.path.join(a.demo_home, 'sessions', slug, s['id'], 'session.jsonl.zstd')
            dst = os.path.join(sdir, f'{s["id"]}.jsonl.zstd'); shutil.copy(src, dst)
            out.append({'id': s['id'], 'title': s['title'], 'sourceCwd': SRC_CWD + demo, 'file': f'.session/{s["id"]}.jsonl.zstd'})
            print(demo, s['title'], os.path.getsize(dst) // 1024, 'KB')
        mp = os.path.join(ddir, 'demo.json'); meta = json.load(open(mp, encoding='utf-8'))
        meta.pop('session', None); meta['sessions'] = out
        json.dump(meta, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

if __name__ == '__main__': main()
