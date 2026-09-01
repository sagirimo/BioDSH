#!/usr/bin/env python3
"""示范项目跑批：在运行中的 BioDSH/dsh 上注册工作区 → 建会话 → 发提示 → 等跑完 → 把对话渲染成 示范对话.md。
用法: run_demo.py --port 2735 --workspace "C:\\Users\\..\\BioDSH\\demos\\01-scrna-analysis" --title "示范 · 单细胞分析与作图" --prompt-file p.txt [--prompt-file p2.txt ...] --out 示范对话.md
从 WSL 调用时用 Windows 的 curl.exe 访问 loopback（WSL 自己的 curl 进不去 host fence）。"""
import argparse, json, subprocess, time, uuid, sys, re, os
CURL = '/mnt/c/Windows/System32/curl.exe' if os.path.exists('/mnt/c/Windows/System32/curl.exe') else 'curl'

def rpc(port, method, payload):
    body = json.dumps({'type': 'client-request', 'rpcId': str(uuid.uuid4()), 'method': method, 'payload': payload}, ensure_ascii=False)
    out = subprocess.run([CURL, '-s', '-X', 'POST', f'http://127.0.0.1:{port}/api/{method}', '-H', 'Content-Type: application/json', '--data-binary', '@-'], input=body.encode('utf-8'), capture_output=True, timeout=120).stdout
    d = json.loads(out.decode('utf-8', 'replace'))
    r = d.get('result', {})
    if not r.get('ok'): raise RuntimeError(f'{method}: {r.get("error")}')
    return r.get('value')

def full_history(port, sid):
    """session.history 只返回尾页；带 beforeSeq 往前翻直到 seq 0。"""
    v = rpc(port, 'session.history', {'sessionId': sid})
    events = list(v['events'])
    guard = 0
    while events and events[0]['event']['seq'] > 0 and guard < 200:
        guard += 1
        older = rpc(port, 'session.history', {'sessionId': sid, 'beforeSeq': events[0]['event']['seq']})['events']
        if not older: break
        events = list(older) + events
    return events

def render(events):
    """history 事件 → markdown：用户消息、助手正文（去掉 reasoning）、工具调用折叠成一行。"""
    md = []
    for e in events:
        ev = e['event']; t = ev['type']; d = ev.get('data', {})
        if t == 'user/message':
            if d.get('source', {}).get('kind') not in (None, 'user'): continue  # 系统注入（技能目录变化等）不算用户消息
            txt = '\n'.join(c.get('text', '') for c in d.get('content', []) if c.get('type') == 'text')
            if not txt.strip() or txt.lstrip().startswith('<system-reminder>'): continue
            md.append(f'\n## 👤 用户\n\n{txt.strip()}\n')
        elif t == 'assistant/message':
            parts = [c.get('text', '') for c in d.get('message', {}).get('content', []) if c.get('type') == 'text']
            txt = '\n'.join(p for p in parts if p.strip())
            if txt.strip(): md.append(f'\n## 🧬 BioDSH\n\n{txt.strip()}\n')
        elif t == 'tool/call':
            name = d.get('name', '?'); args = d.get('arguments', '')
            try: a = json.loads(args) if isinstance(args, str) else args
            except Exception: a = {}
            brief = a.get('command') or a.get('cmd') or a.get('path') or a.get('file_path') or a.get('query') or a.get('pattern') or ''
            if isinstance(brief, str): brief = re.sub(r'\s+', ' ', brief)[:160]
            md.append(f'> 🔧 `{name}` {brief}\n')
    return '\n'.join(md)

def header(title):
    return f'# 示范对话 · {title.replace("示范 · ", "")}\n\n> 这是 BioDSH 里真实发生的一次对话（模型：DeepSeek），原样导出；`🔧` 行是智能体当时调用的工具。你可以在同一个项目里用同样的问法提问。\n'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--port', type=int, required=True); ap.add_argument('--workspace', required=True); ap.add_argument('--title', required=True)
    ap.add_argument('--prompt-file', action='append', required=True); ap.add_argument('--out', required=True); ap.add_argument('--timeout', type=int, default=1800); ap.add_argument('--session', help='续用已有会话')
    ap.add_argument('--render-only', action='store_true', help='不发提示，只把 --session 的历史重新渲染成 markdown')
    a = ap.parse_args()
    if a.render_only:
        hist = full_history(a.port, a.session)
        md = header(a.title) + render(hist)
        open(a.out, 'w', encoding='utf-8').write(md); print('re-rendered', a.out, len(md)); return
    ws = rpc(a.port, 'workspace.create', {'path': a.workspace})
    wid = ws['workspace']['workspaceId']
    if ws.get('created'): rpc(a.port, 'workspace.rename', {'workspaceId': wid, 'title': a.title})
    sid = a.session or rpc(a.port, 'session.create', {'workspaceId': wid})['sessionId']
    print('session', sid, flush=True)
    for pf in a.prompt_file:
        text = open(pf, encoding='utf-8').read().strip()
        rpc(a.port, 'session.prompt', {'sessionId': sid, 'mode': 'queue', 'content': [{'type': 'text', 'text': text}]})
        print('prompt sent:', text[:60].replace('\n', ' '), flush=True)
        t0 = time.time(); time.sleep(8)
        while time.time() - t0 < a.timeout:
            items = rpc(a.port, 'session.list', {})['items']
            me = next((s for s in items if s['sessionId'] == sid), None)
            if me and not me.get('running'): break
            time.sleep(10)
        else:
            print('TIMEOUT waiting for turn', flush=True)
        print(f'turn done in {int(time.time()-t0)}s', flush=True)
    hist = full_history(a.port, sid)
    md = header(a.title) + render(hist)
    open(a.out, 'w', encoding='utf-8').write(md)
    print('wrote', a.out, len(md), 'chars; events', len(hist))

if __name__ == '__main__': main()
