// dsh 兼容自测:拉起打包的 dsh(任意版本)headless,按 shim(lib.rs dsh_raw)完全相同的协议
// 跑一遍 RPC 矩阵,逐项报 通过/坏在哪。升级 dsh 时先跑它——秒级看出哪个方法被破坏,只补那几项。
// 这是"和 dsh 正交"的地基:把耦合面变成一张可回归的清单。
// 用法(在 Windows node 上跑,因为 dsh 有本平台原生模块):
//   node scripts/dsh-compat-test.mjs [--home <tmp dsh-home>] [--patch <cordis.patch.yml>]
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, copyFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : d; };

const dshBin = path.join(root, 'dsh-runtime', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
const dshVer = JSON.parse(readFileSync(path.join(root, 'dsh-runtime', 'node_modules', '@deepseek-ai', 'dsh', 'package.json'), 'utf8')).version;
const home = arg('--home') || mkdtempSync(path.join(tmpdir(), 'dsh-compat-'));
const ws = path.join(home, 'workspace'); mkdirSync(ws, { recursive: true });
const patch = arg('--patch');
if (patch && existsSync(patch)) { mkdirSync(home, { recursive: true }); copyFileSync(patch, path.join(home, 'cordis.patch.yml')); }

const results = [];
const rec = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };

console.log(`# dsh compat test — version ${dshVer}, home ${home}`);
const child = spawn(process.execPath, ['--expose-internals', dshBin, 'web', '--port', '0', '--no-open'], {
  cwd: ws, env: { ...process.env, DSH_HOME: home, DSH_TELEMETRY_DISABLED: '1' },
});
let out = '';
const urlP = new Promise((resolve, reject) => {
  const to = setTimeout(() => reject(new Error('timeout waiting for dsh url')), 40000);
  const scan = (b) => { const s = b.toString(); out += s; if (s.includes('biodsh-router') || s.includes('[BioDSH]')) process.stdout.write(s.split('\n').filter(l => l.includes('biodsh') || l.includes('BioDSH')).join('\n') + '\n'); const m = out.match(/http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9._-]+/); if (m) { clearTimeout(to); resolve(m[0]); } };
  child.stdout.on('data', scan); child.stderr.on('data', scan);
  child.on('exit', (c) => { clearTimeout(to); reject(new Error('dsh exited ' + c + '\n' + out.slice(-500))); });
});

async function main() {
  const tokenUrl = await urlP;
  const origin = new URL(tokenUrl).origin;
  // auth
  const r0 = await fetch(tokenUrl, { redirect: 'manual' });
  const cookie = (r0.headers.getSetCookie?.() || []).map(x => x.split(';')[0]).find(x => x.startsWith('dsh-auth-'));
  rec('auth (303 + dsh-auth cookie)', r0.status === 303 && !!cookie, `status ${r0.status}`);
  const rpc = async (endpoint, wire, args) => {
    const body = { type: 'client-request', rpcId: randomUUID(), method: endpoint, payload: { args: { [wire]: args } } };
    const r = await fetch(`${origin}/api/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: cookie }, body: JSON.stringify(body) });
    try { return (await r.json()).result; } catch { return { ok: false, error: { code: 'non-json', message: (await r.text()).slice(0, 100) } }; }
  };
  const errStr = (res) => JSON.stringify(res?.error || res).slice(0, 160);
  // session/list
  const sl = await rpc('session/list', '_request', {});
  rec('session/list', sl?.ok === true, sl?.ok ? `${(sl.value?.items || []).length} sessions` : errStr(sl));
  // workspace/create (existing dir)
  const wc = await rpc('workspace/create', 'request', { path: ws });
  const wid = wc?.value?.workspace?.workspaceId || wc?.value?.workspaceId;
  rec('workspace/create', wc?.ok === true && !!wid, wc?.ok ? `id ${String(wid).slice(0, 12)}` : errStr(wc));
  // session/create (mounts the agent preset — the persona/preset break shows here)
  const sc = await rpc('session/create', 'request', { workspaceId: wid });
  const sid = sc?.value?.sessionId || sc?.value?.session?.sessionId || sc?.value?.id;
  rec('session/create (preset mounts)', sc?.ok === true && !!sid, sc?.ok ? `sid ${String(sid).slice(0, 14)}` : errStr(sc));
  // session/prompt (envelope boundary — accept = not input-invalid; LLM may still fail on no key)
  if (sid) {
    const sp = await rpc('session/prompt', 'request', { sessionId: sid, mode: 'queue', requestId: randomUUID(), content: [{ type: 'text', text: 'hi' }] });
    const envelopeOk = sp?.ok === true || !/input-invalid|boundary validation|wire field/i.test(errStr(sp));
    rec('session/prompt (envelope accepted)', envelopeOk, sp?.ok ? 'ok' : errStr(sp));
  } else { rec('session/prompt (envelope accepted)', false, 'skipped: no session'); }
  console.log(`\n# ${results.filter(r => r.ok).length}/${results.length} passed`);
}
main().catch(e => { console.error('HARNESS ERROR:', e.message); }).finally(() => {
  if (process.env.BIODSH_ROUTER_DEBUG) { const lines = out.split('\n').filter(l => /skill-router|@biodsh|biodsh|plugin|cannot find|resolve|MODULE_NOT_FOUND|Error/i.test(l)); if (lines.length) console.log('--- dsh log (plugin-related) ---\n' + lines.join('\n')); }
  try { child.kill(); } catch {}
  if (!arg('--home')) { try { rmSync(home, { recursive: true, force: true }); } catch {} }
  setTimeout(() => process.exit(0), 500);
});
