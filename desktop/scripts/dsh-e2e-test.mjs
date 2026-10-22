// dsh 端到端自测(真跑一轮对话):按 dsh.rs ensure_home 的方式拼 BioDSH 的 cordis.patch(精简面板 + preset 覆盖人设 +
// skill-select/step-guard 插件),可选按 lib.rs sync_offline_route 的同一套官方 RPC 配好离线路由,然后发一句提示词、
// 等到回答,检查:有回答、人设生效(回答自称 BioDSH)、离线时确实由 biodsh-offline 路由出的结果。
// 升级 dsh 或改模型路由时跑它;dsh-compat-test 只验协议信封,这个验"真的能用"。
// 用法(Windows node,dsh 有原生模块):
//   node scripts/dsh-e2e-test.mjs --runtime <dir> [--offline <baseURL> <model>]   密钥从环境变量 E2E_API_KEY 读
// 在线模式用 DEEPSEEK_API_KEY 环境变量(写进临时 home 的凭据库)。会产生一两次模型调用的费用。
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, cpSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, '..');
const argv = process.argv;
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const runtime = path.resolve(arg('--runtime', path.join(root, 'dsh-runtime')));
const oi = argv.indexOf('--offline');
const offline = oi >= 0 ? { base: argv[oi + 1], model: argv[oi + 2], key: process.env.E2E_API_KEY || 'local' } : null;
const OFFLINE = 'biodsh-offline';
// --prompt <text>: 换一句提示词;--expect-skill:要求技能精选至少注入一个技能(验证注入路径)
const PROMPT = arg('--prompt', '你是谁？用一句话回答，不要调用任何工具。');
const expectSkill = argv.includes('--expect-skill');
// --attach <tokenUrl>:不自己起 dsh,检查一个正在运行的 BioDSH 应用(路由应已由应用配好,只读检查后发一句话)
const attach = arg('--attach');
const WS = createRequire(path.join(runtime, 'package.json'))('ws');
const dshBin = path.join(runtime, 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
const dshVer = JSON.parse(readFileSync(path.join(runtime, 'node_modules', '@deepseek-ai', 'dsh', 'package.json'), 'utf8')).version;
const home = mkdtempSync(path.join(tmpdir(), 'dsh-e2e-'));
const ws = path.join(home, 'workspace'); mkdirSync(ws, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const rec = (name, ok, detail) => { results.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };

// ---- 与 dsh.rs ensure_home 相同的布局:profile 里启用 dsh-biodsh,home 补丁设默认预设与 biodsh 设置 ----
// appContext 取 dsh.rs 里真正发布的 APP_CONTEXT(按字面注入,不经模板变量)
const rs = readFileSync(path.join(root, 'src-tauri', 'src', 'dsh.rs'), 'utf8');
const APP_CONTEXT = JSON.parse('"' + rs.match(/^const APP_CONTEXT: &str = "((?:[^"\\]|\\.)*)";/m)[1].replace(/\\\r?\n\s*/g, '').replace(/\r?\n/g, '\\n') + '"');
const MINIMAL = ['ui-settings-plugin-inventory', 'ui-settings-plugins', 'ui-cordis', 'ui-brand-official', 'ui-message-feedback', 'ui-reference', 'ui-agent-preset', 'ui-sidebar'];
const template = path.join(runtime, 'node_modules', '@biodsh', 'dsh-biodsh');
if (!existsSync(path.join(template, 'package.json'))) { console.error(`no dsh-biodsh at ${template}; run scripts/stage-dsh.mjs --platforms-only`); process.exit(2); }
const profile = path.join(home, 'profiles', 'web');
cpSync(template, path.join(profile, 'node_modules', 'dsh-biodsh'), { recursive: true });
writeFileSync(path.join(profile, 'package.json'), JSON.stringify({ name: 'dsh-profile-web', private: true, dependencies: {},
  dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', 'dsh-biodsh'] } } }, null, 2));
const body = [
  ...MINIMAL.map((id) => `- id: ${id}\n  disabled: true`),
  '- id: agent-preset-registry\n  config:\n    default: biodsh-ptc',
  `- id: biodsh\n  config:\n    officialSkillsDir: ${JSON.stringify(path.join(root, 'resources', 'skills'))}\n    librarySkillsDir: ${JSON.stringify(path.join(root, 'resources', 'community-skills'))}\n    appContext: ${JSON.stringify(APP_CONTEXT)}\n    debug: true`,
  "- insert:\n    - id: auto-review\n      name: '@deepseek-ai/dsh-experimental-auto-review'",
];
writeFileSync(path.join(home, 'cordis.patch.yml'), `# biodsh e2e\n${body.join('\n')}\n`);
if (!offline) writeFileSync(path.join(home, 'settings.yaml'), 'agent-default-model:\n  provider: deepseek-official\n  model: deepseek-flash\n  reasoningEffort: high\n');

console.log(`# dsh e2e — version ${dshVer}, ${offline ? `offline ${offline.base} ${offline.model}` : 'online deepseek-flash'}, home ${home}`);
const env = { ...process.env, DSH_HOME: home, DSH_TELEMETRY_DISABLED: '1', BIODSH_SELECT_DEBUG: '1' };
delete env.NODE_OPTIONS;
const child = attach ? null : spawn(process.execPath, ['--expose-internals', dshBin, 'web', '--port', '0', '--no-open'], { cwd: ws, env });
let out = '';
const urlP = new Promise((resolve, reject) => {
  const to = setTimeout(() => reject(new Error('timeout waiting for dsh url\n' + out.slice(-800))), 90000);
  const scan = (b) => { out += b.toString(); const m = out.match(/http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9._-]+/); if (m) { clearTimeout(to); resolve(m[0]); } };
  if (attach) { clearTimeout(to); resolve(attach); return; }
  child.stdout.on('data', scan); child.stderr.on('data', scan);
  child.on('exit', (c) => { clearTimeout(to); reject(new Error('dsh exited ' + c + '\n' + out.slice(-800))); });
});

async function main() {
  const tokenUrl = await urlP;
  const origin = new URL(tokenUrl).origin;
  const r0 = await fetch(tokenUrl, { redirect: 'manual' });
  const cookie = (r0.headers.getSetCookie?.() || []).map((x) => x.split(';')[0]).find((x) => x.startsWith('dsh-auth-'));
  rec('boot + auth', !!cookie, `status ${r0.status}`);
  const call = async (endpoint, args) => {
    const r = await fetch(`${origin}/api/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: cookie }, body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method: endpoint, payload: { args } }) });
    return (await r.json().catch(() => null))?.result ?? { ok: false };
  };
  const err = (r) => JSON.stringify(r?.error ?? r).slice(0, 200);

  // 模型路由:与 lib.rs sync_offline_route 相同的调用
  const desc = await call('settings/describe', {});
  const ns = (n) => desc.value?.namespaces?.find((x) => x.ns === n);
  rec('settings/describe', desc.ok === true, desc.ok ? `${desc.value.namespaces.length} namespaces` : err(desc));
  if (attach) {
    const route = ns('llm-pi-ai')?.value?.providers?.[OFFLINE]; const def = ns('agent-default-model')?.value;
    rec('app configured offline route', !!route, route ? `${route.baseURL} ${JSON.stringify(route.models?.map((m) => m.id))}` : 'no biodsh-offline route');
    rec('app default model -> offline route', def?.provider === OFFLINE, JSON.stringify(def));
  } else if (offline) {
    const c = await call('credentials/set', { ref: 'BIODSH_OFFLINE_KEY', value: offline.key });
    const route = { displayName: '本地/内网模型', api: 'openai-completions', baseURL: offline.base, apiKeyEnv: 'BIODSH_OFFLINE_KEY', models: [{ id: offline.model, name: offline.model }] };
    const m1 = await call('settings/mutate', { ns: 'llm-pi-ai', ops: [{ op: 'set', path: ['providers', OFFLINE], value: route }], expectedRevision: ns('llm-pi-ai')?.revision });
    const m2 = await call('settings/mutate', { ns: 'agent-default-model', ops: [{ op: 'set', path: ['provider'], value: OFFLINE }, { op: 'set', path: ['model'], value: offline.model }, { op: 'unset', path: ['reasoningEffort'] }], expectedRevision: ns('agent-default-model')?.revision });
    rec('offline route via settings API', c.ok && m1.ok && m2.ok, [c, m1, m2].filter((x) => !x.ok).map(err).join(' | '));
    const lp = await call('llm/listProviders', {});
    rec('route listed by llm/listProviders', !!lp.value?.some((p) => p.id === OFFLINE), JSON.stringify(lp.value?.map((p) => p.id)));
  } else if (process.env.DEEPSEEK_API_KEY) {
    const c = await call('credentials/set', { ref: 'DEEPSEEK_API_KEY', value: process.env.DEEPSEEK_API_KEY });
    rec('credentials/set DEEPSEEK_API_KEY', c.ok, c.ok ? '' : err(c));
  }

  const wc = await call('workspace/create', { request: { path: ws } });
  const wid = wc.value?.workspace?.workspaceId || wc.value?.workspaceId;
  const sc = await call('session/create', { request: { workspaceId: wid } });
  const sid = sc.value?.sessionId || sc.value?.session?.sessionId;
  rec('workspace + session create', !!sid, sid ? '' : err(sc));
  if (!sid) return;

  // follow 流:激活 agent 并收事件(同 benchmarks/formal_experiment/dsh_run.mjs)
  const st = { answer: '', done: false, reason: '', models: new Set(), events: 0 };
  const ingest = (ev) => {
    if (!ev?.type) return; st.events++;
    const d = ev.data || {};
    for (const k of ['provider', 'model']) { const v = d[k] ?? d.message?.[k] ?? d.usage?.[k]; if (typeof v === 'string') st.models.add(`${k}=${v}`); }
    if (ev.type === 'assistant/message') { const t = (d.message?.content || []).filter((b) => b?.type === 'text').map((b) => b.text || '').join(''); if (t) st.answer = t; }
    else if (ev.type === 'turn/end') { st.done = true; st.reason = typeof d.reason === 'string' ? d.reason : JSON.stringify(d.reason ?? ''); }
  };
  const sock = new WS(origin.replace(/^http/, 'ws') + '/api/remote.mux', { headers: { Cookie: cookie } });
  const streamId = randomUUID();
  let raw = '';
  await new Promise((res, rej) => { sock.on('open', res); sock.on('error', rej); });
  sock.on('message', (data) => {
    const txt = data.toString(); raw += txt.slice(0, 4000) + '\n';
    let msg; try { msg = JSON.parse(txt); } catch { return; }
    if (msg.streamId !== streamId || msg.type !== 'item') return;
    const fr = msg.value;
    if (fr?.type === 'event') ingest(fr.event); else if (fr?.type === 'snapshot') (fr.records || []).forEach((r) => ingest(r.event || r)); else ingest(fr);
  });
  sock.send(JSON.stringify({ type: 'open', streamId, endpoint: 'session/follow', payload: { args: { request: { address: { kind: 'session', sessionId: sid }, assistantStream: true } } } }));
  await sleep(500);
  const sp = await call('session/prompt', { request: { sessionId: sid, mode: 'queue', requestId: randomUUID(), content: [{ type: 'text', text: PROMPT }] } });
  rec('session/prompt accepted', sp.ok === true, sp.ok ? '' : err(sp));
  const t0 = Date.now();
  while (!st.done && Date.now() - t0 < 180000) await sleep(1000);
  try { sock.close(); } catch {}
  rec('turn finished with an answer', st.done && st.answer.trim().length > 0, `${Math.round((Date.now() - t0) / 1000)}s, reason=${st.reason}, answer: ${st.answer.trim().slice(0, 120).replace(/\n/g, ' ')}`);
  if (!expectSkill) rec('persona applied (answer names BioDSH)', /BioDSH/i.test(st.answer), '');
  const routeSeen = offline || attach ? (raw.includes(OFFLINE) || [...st.models].some((m) => m.includes(OFFLINE))) : true;
  if (offline || attach) rec('answer served by biodsh-offline route', routeSeen, [...st.models].join(', ') || '(no provider field in events; searched raw stream)');
  const sel = out.split('\n').filter((l) => l.includes('[biodsh-select]')).slice(0, 3);
  if (!attach) rec('skill-select plugin ran', sel.length > 0, sel.join(' / ').slice(0, 200));
  if (expectSkill) { const picked = out.match(/\[biodsh-select\] picked \[([^\]]*)\]/); rec('skill injected', !!picked?.[1]?.trim(), picked?.[0] ?? 'no pick line'); }
}

main().catch((e) => rec('harness', false, e.message.slice(0, 300))).finally(() => {
  console.log(`\n# ${results.filter((r) => r.ok).length}/${results.length} passed`);
  if (process.env.E2E_FULLLOG) console.log('--- dsh log ---\n' + out.slice(-6000));
  try { child?.kill(); } catch {}
  setTimeout(() => { try { rmSync(home, { recursive: true, force: true }); } catch {} process.exit(results.every((r) => r.ok) ? 0 : 1); }, 800);
});
