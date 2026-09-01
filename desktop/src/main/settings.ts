import { readFileSync, writeFileSync, existsSync, chmodSync } from 'node:fs';
import path from 'node:path';
import type { AppSettings, AppPaths, CredentialStatus } from '../shared/types';

const DEFAULTS: AppSettings = { useChinaMirror: true, workspace: '', onboarded: false, theme: 'system', language: 'system', mode: 'online', offlineBaseUrl: '', offlineModel: '', offlineApiKey: '', remoteDshUrl: '', imageBaseUrl: '', imageApiKey: '', imageModel: '', mcpServers: [], demosSeeded: false };

export function loadSettings(p: AppPaths): AppSettings {
  const f = path.join(p.root, 'settings.json');
  let s: Partial<AppSettings> = {};
  if (existsSync(f)) { try { s = JSON.parse(readFileSync(f, 'utf8')); } catch { /* 损坏则用默认 */ } }
  return { ...DEFAULTS, workspace: p.workspace, ...s };
}

export function saveSettings(p: AppPaths, s: AppSettings): void {
  writeFileSync(path.join(p.root, 'settings.json'), JSON.stringify(s, null, 2));
}

// dsh 的凭据文件：$DSH_HOME/.credentials.yaml。dsh ≥0.1.1 要求版本化布局（version: 1 / refs:），扁平布局会让 dsh 启动失败。
const CRED_KEY = 'DEEPSEEK_API_KEY';

function parseKey(txt: string): string | undefined {
  let inRefs = false;
  const versioned = txt.includes('version:');
  for (const line of txt.split(/\r?\n/)) {
    if (line.startsWith('refs:')) { inRefs = true; continue; }
    if (!/^[ \t]/.test(line)) inRefs = false;
    const m = line.trim().match(new RegExp(`^${CRED_KEY}:\\s*["']?([^"'\\s]+)`));
    if (m && (inRefs || !versioned)) return m[1];
  }
  return undefined;
}
const render = (key?: string) => (key ? `version: 1\n\nrefs:\n  ${CRED_KEY}: ${key}\n` : 'version: 1\n\nrefs: {}\n');

export function readCredentialValue(p: AppPaths): string | undefined {
  const f = path.join(p.dshHome, '.credentials.yaml');
  return existsSync(f) ? parseKey(readFileSync(f, 'utf8')) : undefined;
}

export function readCredential(p: AppPaths): CredentialStatus {
  const k = readCredentialValue(p);
  if (!k) return { hasKey: false };
  return { hasKey: true, masked: k.length > 8 ? `${k.slice(0, 5)}••••${k.slice(-4)}` : '••••' };
}

export function writeCredential(p: AppPaths, apiKey: string): void {
  const f = path.join(p.dshHome, '.credentials.yaml');
  writeFileSync(f, render(apiKey.trim() || undefined));
  try { chmodSync(f, 0o600); } catch { /* Windows 无权限位 */ }
}

export function migrateCredentials(p: AppPaths): void {
  const f = path.join(p.dshHome, '.credentials.yaml');
  if (!existsSync(f)) return;
  const txt = readFileSync(f, 'utf8');
  if (txt.includes('version:') || !txt.trim()) return;
  const k = parseKey(txt);
  if (k) writeFileSync(f, render(k));
}
