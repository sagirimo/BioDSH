import { app, BrowserWindow, WebContentsView, ipcMain, shell, dialog, nativeTheme } from 'electron';
import path from 'node:path';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { appPaths } from './paths';
import { loadSettings, saveSettings, readCredential, writeCredential, readCredentialValue } from './settings';
import { gitStatus, gitInit, gitCommit } from './git';
import { randomUUID } from 'node:crypto';
import { DshManager, setDshTheme, setDshLocale, setDshLlmOverride } from './dsh';
import { PyEnvManager } from './pyenv';
import { SkillStore } from './skills';
import type { AppSettings, IpcEvent, Rect } from '../shared/types';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isMac = process.platform === 'darwin';

let win: BrowserWindow | null = null;
let dshView: WebContentsView | null = null;
let dshVisible = false;
let dshBounds: Rect = { x: 0, y: 0, width: 0, height: 0 };

const paths = appPaths();
let settings = loadSettings(paths);
const broadcast = (e: IpcEvent) => win?.webContents.send('event', e);
const dsh = new DshManager(paths, (status) => broadcast({ type: 'dsh', status }));
const pyenv = new PyEnvManager(paths, (status) => broadcast({ type: 'env', status }));
const store = new SkillStore(paths);

function applyTheme() { nativeTheme.themeSource = settings.theme; }

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: 'BioDSH',
    titleBarStyle: isMac ? 'hiddenInset' : 'hidden',
    trafficLightPosition: { x: 16, y: 18 },
    vibrancy: isMac ? 'sidebar' : undefined,
    visualEffectState: 'active',
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1c1c1e' : '#f5f5f7',
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.once('ready-to-show', () => win?.show());
  // 调试用：BIODSH_SCREENSHOT=/path/a.png BIODSH_SCREENSHOT_TAB=store → 启动后截图并退出
  if (process.env.BIODSH_SCREENSHOT) {
    const shots = process.env.BIODSH_SCREENSHOT.split(',');
    win.webContents.once('did-finish-load', async () => {
      await new Promise((r) => setTimeout(r, Number(process.env.BIODSH_SCREENSHOT_DELAY ?? 8000)));
      const { writeFileSync } = await import('node:fs');
      for (const spec of shots) {
        const [tab, file] = spec.split('=');
        win?.webContents.send('debug:tab', tab);
        await new Promise((r) => setTimeout(r, 1200));
        const img = await win!.webContents.capturePage();
        writeFileSync(file, img.toPNG());
        if (tab === 'chat' && dshView) {
          const img2 = await dshView.webContents.capturePage();
          writeFileSync(file.replace(/\.png$/, '-dsh.png'), img2.toPNG());
          if (process.env.BIODSH_DUMP_DOM) {
            const html = await dshView.webContents.executeJavaScript(`(() => { const walk = (el, d) => { if (d > 7 || !el.tagName) return ''; const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0, 4).join('.') : ''; const attrs = ['data-slot', 'data-testid', 'role', 'aria-label'].map((a) => el.getAttribute && el.getAttribute(a) ? a + '=' + el.getAttribute(a) : '').filter(Boolean).join(' '); const text = el.children.length === 0 ? (el.textContent || '').trim().slice(0, 40) : ''; let out = '  '.repeat(d) + '<' + el.tagName.toLowerCase() + (cls ? ' .' + cls : '') + (attrs ? ' ' + attrs : '') + '>' + (text ? ' ' + JSON.stringify(text) : '') + '\n'; for (const c of el.children) out += walk(c, d + 1); return out; }; return walk(document.body, 0); })()`);
            writeFileSync(process.env.BIODSH_DUMP_DOM, html);
          }
        }
      }
      app.quit();
    });
  }
  win.on('closed', () => { win = null; dshView = null; });
  win.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  win.on('resize', layoutDsh);
  nativeTheme.on('updated', () => win?.webContents.send('theme', nativeTheme.shouldUseDarkColors));

  if (process.env.ELECTRON_RENDERER_URL) win.loadURL(process.env.ELECTRON_RENDERER_URL);
  else win.loadFile(path.join(__dirname, '../renderer/index.html'));
}

// dsh 的网页界面装在一个 WebContentsView 里，叠在我们壳子的内容区上；切换标签时显隐。
function ensureDshView(url: string) {
  if (!win) return;
  if (dshView) {
    if (dshView.webContents.getURL() !== url) dshView.webContents.loadURL(url);
    return;
  }
  dshView = new WebContentsView({ webPreferences: { contextIsolation: true, sandbox: true } });
  dshView.setBackgroundColor(nativeTheme.shouldUseDarkColors ? '#1c1c1e' : '#ffffff');
  dshView.webContents.setWindowOpenHandler(({ url: u }) => { shell.openExternal(u); return { action: 'deny' }; });
  // 精简模式的收尾：补丁层关掉了侧栏插件，但布局仍给它留了一列；这里用 CSS 把空列、拖拽条和首页大标题收掉。
  dshView.webContents.on('dom-ready', () => {
    void dshView?.webContents.insertCSS(`
      [class*="_sidebarCol"] { visibility: hidden !important; overflow: hidden !important; min-width: 0 !important; }
      [class*="_handle"][data-side="left"] { display: none !important; }
      [class*="_headline"], [class*="_heroGlow"] { display: none !important; }
    `);
    // 布局的三列宽度是内联样式（侧栏px / 内容 / 详情px），只把第一列压成 0，详情栏照常可开合。
    void dshView?.webContents.executeJavaScript(`(() => {
      const fix = () => { const f = document.querySelector('[class*="_frame"]'); if (!f) return; const v = f.style.gridTemplateColumns; if (v && !v.startsWith('0px')) f.style.gridTemplateColumns = v.replace(/^\\S+/, '0px'); };
      const mo = new MutationObserver(fix);
      const start = () => { const f = document.querySelector('[class*="_frame"]'); if (!f) { setTimeout(start, 200); return; } mo.observe(f, { attributes: true, attributeFilter: ['style'] }); fix(); };
      start();
    })()`, true);
  });
  dshView.webContents.loadURL(url);
  win.contentView.addChildView(dshView);
  layoutDsh();
}

function layoutDsh() {
  if (!dshView) return;
  if (dshVisible && dshBounds.width > 0) {
    dshView.setVisible(true);
    dshView.setBounds({ x: Math.round(dshBounds.x), y: Math.round(dshBounds.y), width: Math.round(dshBounds.width), height: Math.round(dshBounds.height) });
  } else {
    dshView.setVisible(false);
  }
}

const dshCall = async (method: string, payload: unknown) => {
  const url = dsh.status.url; if (!url) throw new Error('dsh 未运行');
  const r = await fetch(`${url}/api/${method}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method, payload }) });
  const j = await r.json() as { result?: { ok: boolean; value?: unknown; error?: unknown } };
  if (!j.result?.ok) throw new Error(JSON.stringify(j.result?.error ?? 'rpc failed'));
  return j.result.value;
};

function registerIpc() {
  ipcMain.handle('app:info', () => ({
    version: app.getVersion(), dshVersion: (() => { try { return JSON.parse(readFileSync(path.join(path.dirname(require('node:module').createRequire(import.meta.url).resolve('@deepseek-ai/dsh/package.json')), 'package.json'), 'utf8')).version as string; } catch { return '?'; } })(), platform: process.platform, paths, dark: nativeTheme.shouldUseDarkColors,
  }));
  ipcMain.handle('settings:get', () => settings);
  ipcMain.handle('settings:set', (_e, patch: Partial<AppSettings>) => {
    const themeChanged = patch.theme && patch.theme !== settings.theme;
    const langChanged = patch.language && patch.language !== settings.language;
    settings = { ...settings, ...patch };
    saveSettings(paths, settings);
    applyTheme();
    if (langChanged) setDshLocale(paths, settings.language);
    if (themeChanged || langChanged) { setDshTheme(paths, settings.theme); dshView?.webContents.reload(); }
    return settings;
  });
  ipcMain.handle('credential:get', () => readCredential(paths));
  ipcMain.handle('credential:set', async (_e, key: string) => { writeCredential(paths, key); if (dsh.status.state !== 'stopped') { const s = await dsh.restart(settings.workspace || paths.workspace); if (s.state === 'running' && s.url) ensureDshView(s.url); } return readCredential(paths); });
  const openSession = (id: string) => dshView?.webContents.executeJavaScript(`try { localStorage.setItem('dsh.sessions.current', JSON.stringify({ sessionId: ${JSON.stringify(id)} })); } catch (e) {} location.reload();`);
  ipcMain.handle('dsh:rpc', (_e, method: string, payload: unknown) => dshCall(method, payload));
  ipcMain.handle('dsh:openSession', (_e, id: string) => openSession(id));
  ipcMain.handle('dsh:newSession', async (_e, workspaceId: string) => { const v = await dshCall('session.create', { workspaceId }) as { sessionId: string }; await openSession(v.sessionId); return v.sessionId; });
  const dshVersion = () => { try { return JSON.parse(readFileSync(path.join(path.dirname(require('node:module').createRequire(import.meta.url).resolve('@deepseek-ai/dsh/package.json')), 'package.json'), 'utf8')).version as string; } catch { return '?'; } };
  ipcMain.handle('updates:check', async () => {
    const current = dshVersion();
    const latest = await fetch('https://registry.npmmirror.com/@deepseek-ai/dsh').then((r) => r.json()).then((j: { 'dist-tags': { latest: string } }) => j['dist-tags'].latest).catch(() => '?');
    return { dsh: { current, latest, outdated: latest !== '?' && latest !== current }, app: { current: app.getVersion() } };
  });
  ipcMain.handle('assistant:ask', async (_e, model: string, question: string, context: string) => {
    const key = readCredentialValue(paths); if (!key) throw new Error('还没填 API Key，去「更多 → 模型 API Key」填一下');
    const r = await fetch('https://api.deepseek.com/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model, messages: [{ role: 'system', content: `你是 BioDSH 桌面软件的内置向导。用户是不懂生信和编程的医生/实验人员，请用最通俗的中文、不超过 120 字回答，必要时分 1-3 步。当前界面上下文：${context}` }, { role: 'user', content: question }], temperature: 0.3, max_tokens: 400 }) });
    const j = await r.json() as { choices?: { message: { content: string } }[] };
    return j.choices?.[0]?.message.content ?? '没有得到回答';
  });
  ipcMain.handle('files:list', async (_e, p?: string) => {
    const { listWorkspaceFiles } = await import('./files');
    return listWorkspaceFiles(p?.trim() || settings.workspace || paths.workspace);
  });
  ipcMain.handle('migrate:scan', async () => []);
  ipcMain.handle('migrate:import', async () => { throw new Error('Electron 版暂不支持迁移，请使用 Tauri 版'); });
  ipcMain.handle('dsh:deleteSession', async (_e, sessionId: string) => {
    if (!sessionId.startsWith('session-') || /[\/\\.]/.test(sessionId)) throw new Error('非法会话 id');
    await dshCall('workspace.archiveSession', { sessionId }).catch(() => undefined);
    const { readdirSync, rmSync, existsSync: ex } = await import('node:fs');
    const root = path.join(paths.dshHome, 'sessions'); let removed = 0;
    if (ex(root)) for (const d of readdirSync(root)) { const p = path.join(root, d, sessionId); if (ex(p)) { rmSync(p, { recursive: true, force: true }); removed++; } }
    return removed;
  });
  ipcMain.handle('env:installExtra', async (_e, _packages: string[]) => { throw new Error('Electron 版暂不支持扩展包安装，请使用 Tauri 版'); });
  ipcMain.handle('refdata:list', async () => []);
  ipcMain.handle('refdata:install', async () => { throw new Error('Electron 版暂不支持本地参考包，请使用 Tauri 版'); });
  ipcMain.handle('refdata:remove', async () => []);
  ipcMain.handle('demos:seed', async () => []);
  ipcMain.handle('dsh:setContext', async () => undefined);
  const ratingsPath = () => path.join(paths.root, 'ratings.json');
  const ratingsGet = () => { try { return JSON.parse(readFileSync(ratingsPath(), 'utf8')); } catch { return {}; } };
  ipcMain.handle('ratings:get', () => ratingsGet());
  ipcMain.handle('ratings:set', (_e, id: string, vote: number, comment: string) => {
    const all = ratingsGet() as Record<string, unknown>;
    if (vote === 0) delete all[id]; else all[id] = { vote, comment, at: Math.floor(Date.now() / 1000) };
    writeFileSync(ratingsPath(), JSON.stringify(all, null, 2));
    return all;
  });
  ipcMain.handle('files:readImage', async (_e, rel: string, wsPath?: string) => {
    const { realpathSync } = await import('node:fs');
    const root = realpathSync(wsPath?.trim() || settings.workspace || paths.workspace);
    const p = realpathSync(path.join(root, rel));
    if (!p.startsWith(root)) throw new Error('路径越界');
    const buf = readFileSync(p);
    if (buf.length > 3_000_000) throw new Error('图片太大');
    const ext = p.split('.').pop()?.toLowerCase();
    const mime = ext === 'png' ? 'image/png' : ext === 'svg' ? 'image/svg+xml' : 'image/jpeg';
    return `data:${mime};base64,${buf.toString('base64')}`;
  });
  ipcMain.handle('dsh:export', async (_e, sessionId: string) => {
    if (!win || !dsh.status.url) return null;
    const r = await dialog.showSaveDialog(win, { defaultPath: `biodsh-对话-${sessionId.slice(0, 12)}.zip`, filters: [{ name: '对话记录', extensions: ['zip'] }] });
    if (r.canceled || !r.filePath) return null;
    const res = await fetch(`${dsh.status.url}/api/session.export?sessionId=${encodeURIComponent(sessionId)}&includeDescendants=true`);
    writeFileSync(r.filePath, Buffer.from(await res.arrayBuffer()));
    return r.filePath;
  });
  ipcMain.handle('git:status', (_e, p: string) => gitStatus(p));
  ipcMain.handle('git:init', (_e, p: string) => gitInit(p));
  ipcMain.handle('git:commit', (_e, p: string, m: string) => gitCommit(p, m));
  ipcMain.handle('deepseek:balance', async () => {
    if (settings.mode === 'offline') throw new Error('offline-mode');
    const key = readCredentialValue(paths); if (!key) throw new Error('no-key');
    const r = await fetch('https://api.deepseek.com/user/balance', { headers: { Authorization: `Bearer ${key}` } });
    return r.json();
  });

  ipcMain.handle('env:status', () => pyenv.probe());
  ipcMain.handle('env:install', () => pyenv.install(settings.useChinaMirror));

  ipcMain.handle('dsh:status', () => dsh.status);
  ipcMain.handle('dsh:start', async () => {
    setDshTheme(paths, settings.theme); setDshLocale(paths, settings.language);
    const offline = settings.mode === 'offline';
    setDshLlmOverride(paths, offline && settings.offlineBaseUrl?.trim() ? { baseUrl: settings.offlineBaseUrl.trim(), model: settings.offlineModel?.trim() ?? '' } : null);
    if (offline && settings.remoteDshUrl?.trim()) {
      dsh.status.state = 'running'; dsh.status.url = settings.remoteDshUrl.trim();
      ensureDshView(dsh.status.url);
      return dsh.status;
    }
    const s = await dsh.start(settings.workspace || paths.workspace, offline ? (settings.offlineApiKey || 'local') : undefined);
    if (s.state === 'running' && s.url) { const v = await dshCall('workspace.create', { path: settings.workspace || paths.workspace }).catch(() => undefined) as { created?: boolean; workspace?: { workspaceId: string } } | undefined; if (v?.created && v.workspace) await dshCall('workspace.rename', { workspaceId: v.workspace.workspaceId, title: '我的分析' }).catch(() => undefined); ensureDshView(s.url); }
    return s;
  });
  ipcMain.handle('dsh:restart', async () => {
    const s = await dsh.restart(settings.workspace || paths.workspace);
    if (s.state === 'running' && s.url) ensureDshView(s.url);
    return s;
  });
  ipcMain.handle('dsh:reload', () => dshView?.webContents.reload());
  ipcMain.on('dsh:bounds', (_e, rect: Rect, visible: boolean) => { dshBounds = rect; dshVisible = visible; layoutDsh(); });

  ipcMain.handle('skills:catalog', () => store.catalog());
  ipcMain.handle('skills:statuses', () => store.statuses());
  ipcMain.handle('skills:readme', (_e, id: string) => store.readme(id));
  ipcMain.handle('skills:install', (_e, id: string) => {
    const r = store.install(id);
    broadcast({ type: 'skills', statuses: store.statuses() });
    return r;
  });
  ipcMain.handle('skills:uninstall', (_e, id: string) => {
    const r = store.uninstall(id);
    broadcast({ type: 'skills', statuses: store.statuses() });
    return r;
  });

  ipcMain.handle('shell:openPath', (_e, p: string) => shell.openPath(p));
  ipcMain.handle('shell:openExternal', (_e, u: string) => shell.openExternal(u));
  ipcMain.handle('dialog:pickFolder', async () => {
    if (!win) return null;
    const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] });
    return r.canceled ? null : r.filePaths[0];
  });
  ipcMain.handle('window:minimize', () => win?.minimize());
  ipcMain.handle('window:maximize', () => (win?.isMaximized() ? win.unmaximize() : win?.maximize()));
  ipcMain.handle('window:close', () => win?.close());
}

app.whenReady().then(() => {
  applyTheme();
  registerIpc();
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (!isMac) app.quit(); });
app.on('before-quit', () => { void dsh.stop(); });
