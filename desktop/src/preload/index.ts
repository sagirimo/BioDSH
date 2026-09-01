import { contextBridge, ipcRenderer } from 'electron';
import type { AppSettings, IpcEvent, Rect, RefPack, DemoInfo } from '../shared/types';

const api = {
  appInfo: () => ipcRenderer.invoke('app:info'),
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (patch: Partial<AppSettings>) => ipcRenderer.invoke('settings:set', patch),
  getCredential: () => ipcRenderer.invoke('credential:get'),
  setCredential: (key: string) => ipcRenderer.invoke('credential:set', key),
  envStatus: () => ipcRenderer.invoke('env:status'),
  envInstall: () => ipcRenderer.invoke('env:install'),
  dshStatus: () => ipcRenderer.invoke('dsh:status'),
  dshStart: () => ipcRenderer.invoke('dsh:start'),
  dshRestart: () => ipcRenderer.invoke('dsh:restart'),
  dshReload: () => ipcRenderer.invoke('dsh:reload'),
  dshBounds: (rect: Rect, visible: boolean) => ipcRenderer.send('dsh:bounds', rect, visible),
  skillsCatalog: () => ipcRenderer.invoke('skills:catalog'),
  skillsStatuses: () => ipcRenderer.invoke('skills:statuses'),
  skillReadme: (id: string) => ipcRenderer.invoke('skills:readme', id),
  skillInstall: (id: string) => ipcRenderer.invoke('skills:install', id),
  skillUninstall: (id: string) => ipcRenderer.invoke('skills:uninstall', id),
  openPath: (p: string) => ipcRenderer.invoke('shell:openPath', p),
  openExternal: (u: string) => ipcRenderer.invoke('shell:openExternal', u),
  pickFolder: () => ipcRenderer.invoke('dialog:pickFolder'),
  dshRpc: (method: string, payload: unknown = {}) => ipcRenderer.invoke('dsh:rpc', method, payload),
  dshOpenSession: (sessionId: string) => ipcRenderer.invoke('dsh:openSession', sessionId),
  dshNewSession: (workspaceId: string) => ipcRenderer.invoke('dsh:newSession', workspaceId),
  gitStatus: (path: string) => ipcRenderer.invoke('git:status', path),
  gitInit: (path: string) => ipcRenderer.invoke('git:init', path),
  gitCommit: (path: string, message: string) => ipcRenderer.invoke('git:commit', path, message),
  deepseekBalance: () => ipcRenderer.invoke('deepseek:balance'),
  workspaceFiles: (path?: string) => ipcRenderer.invoke('files:list', path),
  migrateScan: () => ipcRenderer.invoke('migrate:scan'),
  migrateImport: (sourceId: string) => ipcRenderer.invoke('migrate:import', sourceId),
  sessionDelete: (sessionId: string) => ipcRenderer.invoke('dsh:deleteSession', sessionId),
  envInstallExtra: (packages: string[]) => ipcRenderer.invoke('env:installExtra', packages),
  refdataList: (): Promise<RefPack[]> => ipcRenderer.invoke('refdata:list'),
  refdataInstall: (id: string): Promise<RefPack> => ipcRenderer.invoke('refdata:install', id),
  refdataRemove: (id: string): Promise<RefPack[]> => ipcRenderer.invoke('refdata:remove', id),
  demosSeed: (): Promise<DemoInfo[]> => ipcRenderer.invoke('demos:seed'),
  dshSetContext: (workspaces: Record<string, string>): Promise<void> => ipcRenderer.invoke('dsh:setContext', workspaces),
  ratingsGet: () => ipcRenderer.invoke('ratings:get'),
  ratingsSet: (id: string, vote: number, comment: string) => ipcRenderer.invoke('ratings:set', id, vote, comment),
  readWorkspaceImage: (rel: string, path?: string) => ipcRenderer.invoke('files:readImage', rel, path),
  sessionExport: (sessionId: string) => ipcRenderer.invoke('dsh:export', sessionId),
  checkUpdates: () => ipcRenderer.invoke('updates:check'),
  assistantAsk: (model: string, question: string, context: string) => ipcRenderer.invoke('assistant:ask', model, question, context),
  windowControl: (a: 'minimize' | 'maximize' | 'close') => ipcRenderer.invoke(`window:${a}`),
  onEvent: (cb: (e: IpcEvent) => void) => {
    const h = (_: unknown, e: IpcEvent) => cb(e);
    ipcRenderer.on('event', h);
    return () => { ipcRenderer.removeListener('event', h); };
  },
  onDebugTab: (cb: (tab: string) => void) => { ipcRenderer.on('debug:tab', (_, t: string) => cb(t)); },
  onTheme: (cb: (dark: boolean) => void) => {
    const h = (_: unknown, d: boolean) => cb(d);
    ipcRenderer.on('theme', h);
    return () => { ipcRenderer.removeListener('theme', h); };
  },
};

contextBridge.exposeInMainWorld('biodsh', api);
export type BiodshApi = typeof api;
