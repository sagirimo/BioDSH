// End-to-end install test through DeepSeek Harness's own plugin manager, the same path as the Plugins page and the
// plugin_manager tool: fresh DSH_HOME -> pluginManager/inspect + installBundle(<spec>) -> restart dsh -> the BioDSH
// preset is listed -> a session on that preset answers with the BioDSH persona, has skill_library, and skill selection
// injects a skill for a bioinformatics request.
// usage: node scripts/install-test.mjs --dsh <runtime dir> --spec <tarball path | npm name | git url> [--pnpm-dir <dir>] [--keep]
//        (DEEPSEEK_API_KEY in env)
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const arg = (k, d) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : d; };
const runtime = path.resolve(arg('--dsh'));
const spec = arg('--spec');
const keep = process.argv.includes('--keep');
const pnpmDir = arg('--pnpm-dir'); // directory holding a pnpm executable, prepended to PATH (the plugin manager runs `pnpm`)
const WS = createRequire(path.join(runtime, 'package.json'))('ws');
const bin = path.join(runtime, 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
const reuse = arg('--home'); // existing home with the bundle installed: skip the install steps
const home = reuse ?? mkdtempSync(path.join(tmpdir(), 'dsh-biodsh-install-'));
const ws = path.join(home, 'workspace'); mkdirSync(ws, { recursive: true });
if (!reuse) writeFileSync(path.join(home, 'settings.yaml'), 'agent-default-model:\n  provider: deepseek-official\n  model: deepseek-flash\n  reasoningEffort: high\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const rec = (n, ok, d = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${d ? '  — ' + d : ''}`); };
let log = '';

function start() {
  const env = { ...process.env, DSH_HOME: home, DSH_TELEMETRY_DISABLED: '1', BIODSH_SELECT_DEBUG: '1' }; delete env.NODE_OPTIONS;
  if (pnpmDir) env.PATH = `${pnpmDir}${path.delimiter}${env.PATH ?? env.Path ?? ''}`;
  const child = spawn(process.execPath, ['--expose-internals', bin, 'web', '--port', '0', '--no-open'], { cwd: ws, env });
  const url = new Promise((res, rej) => {
    const to = setTimeout(() => rej(new Error('dsh did not start\n' + log.slice(-1500))), 120000);
    const scan = (b) => { log += b; const m = log.match(/http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9._-]+/g); if (m && m.length > (child.seen ?? 0)) { child.seen = m.length; clearTimeout(to); res(m[m.length - 1]); } };
    child.stdout.on('data', scan); child.stderr.on('data', scan);
  });
  return { child, url };
}
async function connect(tokenUrl) {
  const origin = new URL(tokenUrl).origin;
  const r0 = await fetch(tokenUrl, { redirect: 'manual' });
  const cookie = (r0.headers.getSetCookie?.() || []).map((x) => x.split(';')[0]).find((x) => x.startsWith('dsh-auth-'));
  const call = async (ep, args, timeout = 60000) => {
    const r = await fetch(`${origin}/api/${ep}`, { method: 'POST', signal: AbortSignal.timeout(timeout), headers: { 'Content-Type': 'application/json', Cookie: cookie },
      body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method: ep, payload: { args } }) });
    return (await r.json().catch(() => null))?.result ?? { ok: false };
  };
  return { origin, cookie, call };
}
const err = (r) => JSON.stringify(r?.error ?? r).slice(0, 300);

async function main() {
  let dsh = start();
  let c = await connect(await dsh.url);
  if (process.env.DEEPSEEK_API_KEY) await c.call('credentials/set', { ref: 'DEEPSEEK_API_KEY', value: process.env.DEEPSEEK_API_KEY });
  if (!reuse) {
  const ins = await c.call('pluginManager/inspect', { spec, options: {} }, 120000);
  rec('pluginManager/inspect', ins.ok && !ins.value?.problem && ins.value?.bundle !== false, JSON.stringify(ins.value ?? ins.error).slice(0, 200));
  const t0 = Date.now();
  const inst = await c.call('pluginManager/installBundle', { spec, options: { requestId: randomUUID() } }, 900000);
  const applied = inst.ok === true && !['failed', 'cancelled'].includes(inst.value?.application);
  rec('pluginManager/installBundle', applied, `${Math.round((Date.now() - t0) / 1000)}s ` + JSON.stringify(inst.value ?? inst.error).slice(0, applied ? 200 : 2500));
  const lb = await c.call('pluginManager/listBundles', {});
  const ours = (lb.value || []).find((b) => b.name === 'dsh-biodsh');
  rec('bundle listed and enabled', !!ours?.enabled && !ours?.error, JSON.stringify({ enabled: ours?.enabled, error: ours?.error, meta: ours?.meta?.title ?? ours?.meta }).slice(0, 200));

  // the running composition picks bundles up at the next start (no HMR in a plain `dsh web`)
  dsh.child.kill(); await sleep(3000);
  dsh = start(); c = await connect(await dsh.url);
  }
  const pl = await c.call('agentPresets/list', {});
  const presets = Array.isArray(pl.value) ? pl.value : (pl.value?.items ?? pl.value?.presets ?? []);
  const ids = presets.map((p) => p.id ?? p.agentPreset ?? p);
  const bio = presets.find((p) => (p.id ?? p) === 'biodsh');
  rec('BioDSH preset listed (standard kept)', ids.includes('biodsh') && ids.includes('standard'), JSON.stringify(ids) + (ids.length ? '' : ' raw ' + JSON.stringify(pl).slice(0, 300)) + (bio?.error ? ' error ' + JSON.stringify(bio.error).slice(0, 200) : ''));

  const desc = await c.call('settings/describe', {});
  const nsB = desc.value?.namespaces?.find((n) => n.ns === 'biodsh');
  rec('settings namespace biodsh', !!nsB, nsB ? JSON.stringify(nsB.value).slice(0, 160) : 'missing');
  if (nsB) {
    const mu = await c.call('settings/mutate', { ns: 'biodsh', ops: [{ op: 'set', path: ['guardSoftSteps'], value: 41 }], expectedRevision: nsB.revision });
    rec('settings/mutate biodsh.guardSoftSteps', mu.ok === true && mu.value?.value?.guardSoftSteps === 41, mu.ok ? '' : err(mu));
  }
  const wc = await c.call('workspace/create', { request: { path: ws } });
  const wid = wc.value?.workspace?.workspaceId || wc.value?.workspaceId;
  const sc = await c.call('session/create', { request: { workspaceId: wid, agentPreset: 'biodsh' } });
  const sid = sc.value?.sessionId || sc.value?.session?.sessionId;
  rec('session on BioDSH preset', !!sid, sid ? JSON.stringify(sc.value?.agentPreset ?? '') : err(sc));
  if (!sid) return;
  const st = { answer: '', done: false, tools: new Set(), injected: [], events: 0 };
  const ingest = (ev) => {
    if (!ev?.type) return; st.events++;
    const d = ev.data || {};
    if (ev.type === 'assistant/message') { const t = (d.message?.content || []).filter((b) => b?.type === 'text').map((b) => b.text).join(''); if (t) st.answer = t; }
    if (ev.type === 'user/message' && d.source?.kind === 'skill-invocation') st.injected.push(d.source.name);
    if (ev.type === 'request/header' || ev.type === 'request/context') for (const m of JSON.stringify(d).matchAll(/"name":"(skill_library|skill)"/g)) st.tools.add(m[1]);
    if (ev.type === 'turn/end') st.done = true;
  };
  const sock = new WS(c.origin.replace(/^http/, 'ws') + '/api/remote.mux', { headers: { Cookie: c.cookie } });
  const streamId = randomUUID();
  await new Promise((res, rej) => { sock.on('open', res); sock.on('error', rej); });
  sock.on('message', (data) => {
    let msg; try { msg = JSON.parse(data.toString()); } catch { return; }
    if (msg.streamId !== streamId || msg.type !== 'item') return;
    const fr = msg.value;
    if (fr?.type === 'event') ingest(fr.event); else if (fr?.type === 'snapshot') (fr.records || []).forEach((r) => ingest(r.event || r)); else ingest(fr);
  });
  sock.send(JSON.stringify({ type: 'open', streamId, endpoint: 'session/follow', payload: { args: { request: { address: { kind: 'session', sessionId: sid }, assistantStream: true } } } }));
  await sleep(500);
  await c.call('session/prompt', { request: { sessionId: sid, mode: 'queue', requestId: randomUUID(),
    content: [{ type: 'text', text: '我有一个单细胞 h5ad 文件，想做质控、聚类和细胞类型注释。先别动手，用两句话说你是谁、会按哪个技能的流程做。' }] } });
  const t1 = Date.now();
  while (!st.done && Date.now() - t1 < 180000) await sleep(1000);
  try { sock.close(); } catch {}
  rec('answered on BioDSH preset', st.done && !!st.answer.trim(), st.answer.trim().slice(0, 160).replace(/\n/g, ' '));
  rec('persona (names BioDSH)', /BioDSH/.test(st.answer));
  rec('skill selection injected a skill', st.injected.length > 0, JSON.stringify(st.injected));
  const sel = log.split('\n').filter((l) => l.includes('[biodsh-select]')).slice(-2).join(' / ');
  console.log('      select log:', sel.slice(0, 300));
  dsh.child.kill();
}
main().catch((e) => rec('harness', false, e.message.slice(0, 400))).finally(async () => {
  console.log(`\n# ${results.filter(Boolean).length}/${results.length} passed  (home ${home})`);
  if (process.env.INSTALL_TEST_LOG) console.log(log.slice(-5000));
  await sleep(1500);
  if (!keep && !reuse) try { rmSync(home, { recursive: true, force: true }); } catch {}
  process.exit(results.every(Boolean) ? 0 : 1);
});
