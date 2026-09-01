// Tauri 桥：把 window.biodsh 接口实现为 invoke/listen，与 Electron preload 暴露的接口保持一致。
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { AppSettings, IpcEvent, Rect } from '@shared/types';

export function installTauriBridge() {
  const api = {
    mode: 'tauri' as const,
    appInfo: () => invoke('app_info'),
    getSettings: () => invoke('settings_get'),
    setSettings: (patch: Partial<AppSettings>) => invoke('settings_set', { patch }),
    getCredential: () => invoke('credential_get'),
    setCredential: (key: string) => invoke('credential_set', { key }),
    envStatus: () => invoke('env_status'),
    envInstall: () => invoke('env_install'),
    dshStatus: () => invoke('dsh_status'),
    dshStart: () => invoke('dsh_start'),
    dshRestart: () => invoke('dsh_restart'),
    dshReload: () => invoke('dsh_reload'),
    dshBounds: (rect: Rect, visible: boolean) => { void invoke('dsh_bounds', { rect, visible }); },
    skillsCatalog: () => invoke('skills_catalog'),
    skillsStatuses: () => invoke('skills_statuses'),
    skillReadme: (id: string) => invoke('skills_readme', { id }),
    skillInstall: (id: string) => invoke('skills_install', { id }),
    skillUninstall: (id: string) => invoke('skills_uninstall', { id }),
    openPath: (p: string) => invoke('open_path', { path: p }),
    openExternal: (u: string) => invoke('open_external', { url: u }),
    pickFolder: () => invoke('pick_folder'),
    dshRpc: (method: string, payload: unknown = {}) => invoke('dsh_rpc', { method, payload }),
    dshOpenSession: (sessionId: string) => invoke('dsh_open_session', { sessionId }),
    dshNewSession: (workspaceId: string) => invoke('dsh_new_session', { workspaceId }),
    gitStatus: (path: string) => invoke('git_status', { path }),
    gitInit: (path: string) => invoke('git_init', { path }),
    gitCommit: (path: string, message: string) => invoke('git_commit', { path, message }),
    deepseekBalance: () => invoke('deepseek_balance'),
    workspaceFiles: (path?: string) => invoke('workspace_files', { path: path ?? null }),
    migrateScan: () => invoke('migrate_scan'),
    migrateImport: (sourceId: string) => invoke('migrate_import', { sourceId }),
    sessionDelete: (sessionId: string) => invoke('session_delete', { sessionId }),
    envInstallExtra: (packages: string[]) => invoke('env_install_extra', { packages }),
    refdataList: () => invoke('refdata_list'),
    refdataInstall: (id: string) => invoke('refdata_install', { id }),
    refdataRemove: (id: string) => invoke('refdata_remove', { id }),
    demosSeed: () => invoke('demos_seed'),
    dshSetContext: (workspaces: Record<string, string>) => invoke('dsh_set_context', { workspaces }),
    ratingsGet: () => invoke('ratings_get'),
    ratingsSet: (id: string, vote: number, comment: string) => invoke('ratings_set', { id, vote, comment }),
    readWorkspaceImage: (rel: string, path?: string) => invoke('read_workspace_image', { rel, path: path ?? null }),
    sessionExport: (sessionId: string) => invoke('session_export', { sessionId }),
    checkUpdates: () => invoke('check_updates'),
    assistantAsk: (model: string, question: string, context: string) => invoke('assistant_ask', { model, question, context }),
    windowControl: (a: 'minimize' | 'maximize' | 'close') => invoke('window_control', { action: a }),
    onEvent: (cb: (e: IpcEvent) => void) => {
      const p = listen<IpcEvent>('event', (e) => cb(e.payload));
      return () => { void p.then((un) => un()); };
    },
    onDebugTab: (_cb: (tab: string) => void) => { /* Tauri 版无截图调试 */ },
    onTheme: (_cb: (dark: boolean) => void) => () => { /* 用 CSS 媒体查询即可 */ },
  };
  (window as unknown as { biodsh: typeof api }).biodsh = api;
  const log = (m: string) => { void invoke('client_log', { line: `${new Date().toISOString()} ${m}` }); };
  window.addEventListener('error', (e) => log(`error: ${e.message} @${e.filename}:${e.lineno}`));
  window.addEventListener('unhandledrejection', (e) => log(`unhandledrejection: ${String((e as PromiseRejectionEvent).reason)}`));
  log('bridge installed');
  // 顶栏拖拽：Tauri 无边框窗口靠 data-tauri-drag-region 属性
  const mark = () => document.querySelectorAll('.drag').forEach((el) => el.setAttribute('data-tauri-drag-region', ''));
  new MutationObserver(mark).observe(document.documentElement, { childList: true, subtree: true });
  mark();
}
