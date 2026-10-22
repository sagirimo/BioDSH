import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, ChevronDown, ChevronRight, Pin, Pencil, Archive, Share2, Trash2, FolderOpen, Sparkles, GitBranch, GitCommitHorizontal, X } from 'lucide-react';
import { BioIcon, fileIconFor } from '../icons';
import { useApp } from '../store';
import ContextMenu, { type MenuState } from './ContextMenu';
import { useT } from '../i18n';

// 项目-任务树：项目 = dsh 工作区（一个文件夹），任务 = 该工作区里的一个 dsh 会话。
interface Workspace { workspaceId: string; path: string; title: string; sessionIds: string[]; updatedAt: string }
interface SessionRow { sessionId: string; updatedAt: number; running: boolean; blank: boolean; cwd?: string; agentAvailable?: boolean; projections?: { values: Record<string, unknown> } }
interface GitInfo { available: boolean; isRepo: boolean; branch?: string; dirty: number; lastCommit?: string }
interface Balance { total?: string; granted?: string; topped?: string; currency?: string; error?: string }
interface FileEntry { name: string; rel: string; size: number; modified: number; kind: string }

function sessionTitle(s: SessionRow): string {
  const t = s.projections?.values?.title;
  if (typeof t === 'string' && t.trim()) return t;
  // 旧版 dsh 录制的会话 0.2 读不出投影（没有标题），标出来而不是显示成未命名
  if (!s.projections && s.agentAvailable === false) return '旧版任务（只读）';
  return s.blank ? '新任务' : '未命名任务';
}
function sessionTokens(s: SessionRow): number {
  const u = s.projections?.values?.tokenUsage as { uncachedInputTokens?: number; outputTokens?: number; cacheReadTokens?: number } | undefined;
  return u ? (u.uncachedInputTokens ?? 0) + (u.outputTokens ?? 0) + (u.cacheReadTokens ?? 0) : 0;
}
const fmtTokens = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n));
const fmtSize = (n: number) => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);
const fmtDay = (ms: number) => { const d = new Date(ms); return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`; };
const loadPins = (): string[] => { try { return JSON.parse(localStorage.getItem('biodsh.pins') ?? '[]'); } catch { return []; } };
// 生成物：图片、或放在常见输出目录里的文件
const isResult = (f: FileEntry) => f.kind === 'image' || /^(results?|outputs?|figures?|figs|plots|submission|reports?)\//i.test(f.rel);

export default function Sidebar() {
  const { tab, setTab, dsh, settings, currentSession: current, setCurrentSession: setCurrent, setTaskMeta } = useApp();
  const offline = settings?.mode === 'offline';
  const { t, lang } = useT();
  const api = window.biodsh;
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [sessions, setSessions] = useState<Record<string, SessionRow>>({});
  const [archived, setArchived] = useState<Set<string>>(new Set());
  const [git, setGit] = useState<Record<string, GitInfo>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [pins, setPins] = useState<string[]>(loadPins);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [usageOpen, setUsageOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [fileTab, setFileTab] = useState<'data' | 'results'>('data');

  const toast = (m: string) => { setNotice(m); setTimeout(() => setNotice(null), 4000); };
  const savePins = (p: string[]) => { setPins(p); try { localStorage.setItem('biodsh.pins', JSON.stringify(p)); } catch { /* */ } };

  const refresh = useCallback(async (manual = false) => {
    if (dsh.state !== 'running') { if (manual) toast(t('智能体还没运行')); return; }
    if (manual) setRefreshing(true);
    try {
      const [ws, ss] = await Promise.all([
        api.dshRpc('workspace.list') as Promise<{ items: Workspace[]; archivedSessionIds: string[] }>,
        api.dshRpc('session.list') as Promise<{ items: SessionRow[] }>,
      ]);
      setWorkspaces(ws.items); setArchived(new Set(ws.archivedSessionIds));
      // 告诉 dsh 视图「工作区标题 → 路径」，对话里提到的图片文件才能拼出地址显示缩略图
      try { await api.dshSetContext(Object.fromEntries(ws.items.map((w) => [w.title, w.path]))); } catch { /* electron 版无此功能 */ }
      setSessions(Object.fromEntries(ss.items.map((s) => [s.sessionId, s])));
      const g: Record<string, GitInfo> = {};
      await Promise.all(ws.items.map(async (w) => { g[w.workspaceId] = (await api.gitStatus(w.path)) as GitInfo; }));
      setGit(g);
    } catch (e) { if (manual) toast(t('刷新失败：{msg}', { msg: String(e).slice(0, 80) })); }
    finally { if (manual) setTimeout(() => setRefreshing(false), 400); }
  }, [dsh.state, lang]);

  useEffect(() => { void refresh(); const timer = setInterval(() => { void refresh(); }, 5000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => {
    let alive = true;
    const load = () => api.deepseekBalance().then((b: { balance_infos?: { currency: string; total_balance: string; granted_balance: string; topped_up_balance: string }[] }) => {
      if (!alive) return; const i = b.balance_infos?.[0]; setBalance(i ? { total: i.total_balance, granted: i.granted_balance, topped: i.topped_up_balance, currency: i.currency } : { error: t('无数据') });
    }).catch((e: unknown) => alive && setBalance({ error: String(e).includes('no-key') ? t('未填 API Key') : t('查询失败') }));
    load(); const timer = setInterval(load, 60_000); return () => { alive = false; clearInterval(timer); };
  }, [lang]);

  // 启动后还没选中任务时，跟随 dsh 打开的最近一个任务，标题栏才有路径和名称
  useEffect(() => {
    if (current) return;
    const recent = Object.values(sessions).filter((s) => !archived.has(s.sessionId) && workspaces.some((w) => w.sessionIds.includes(s.sessionId))).sort((a, b) => b.updatedAt - a.updatedAt)[0];
    if (recent) setCurrent(recent.sessionId);
  }, [sessions, workspaces, archived, current]);
  const currentWs = useMemo(() => workspaces.find((w) => current && w.sessionIds.includes(current)) ?? workspaces[0], [workspaces, current]);
  // 标题栏要显示的当前任务信息
  useEffect(() => {
    const s = current ? sessions[current] : undefined;
    const w = workspaces.find((x) => current && x.sessionIds.includes(current));
    setTaskMeta(s && w ? { sessionId: s.sessionId, title: t(sessionTitle(s)), project: w.title || w.path.split(/[\\/]/).pop() || '', projectPath: w.path, running: s.running, blank: s.blank } : null);
  }, [current, sessions, workspaces, lang]);
  // 当前项目的文件
  useEffect(() => {
    if (!currentWs) { setFiles([]); return; }
    let alive = true;
    const load = () => (api.workspaceFiles(currentWs.path) as Promise<FileEntry[]>).then((f) => alive && setFiles(f.sort((a, b) => b.modified - a.modified))).catch(() => alive && setFiles([]));
    void load(); const timer = setInterval(load, 15_000); return () => { alive = false; clearInterval(timer); };
  }, [currentWs?.path]);

  const openSession = (id: string) => { setCurrent(id); setTab('chat'); void api.dshOpenSession(id); };
  const newSession = async (workspaceId?: string) => {
    const ws = workspaceId ?? currentWs?.workspaceId; if (!ws || busy) return;
    const w = workspaces.find((x) => x.workspaceId === ws);
    const blank = w?.sessionIds.map((id) => sessions[id]).filter((s): s is SessionRow => !!s && s.blank && !archived.has(s.sessionId)).sort((a, b) => b.updatedAt - a.updatedAt)[0];
    if (blank) { openSession(blank.sessionId); return; }
    setBusy(true);
    try { const id = await api.dshNewSession(ws) as string; setCurrent(id); setTab('chat'); await refresh(); } catch (e) { toast(t('新建失败：{msg}', { msg: String(e).slice(0, 80) })); } finally { setBusy(false); }
  };
  const addProject = async () => {
    if (dsh.state !== 'running') { toast(t('智能体还没运行，稍等')); return; }
    try {
      const p = await api.pickFolder(); if (!p) return;
      await api.dshRpc('workspace.create', { path: p }); await refresh(true); toast(t('已添加项目'));
    } catch (e) { toast(t('添加失败：{msg}', { msg: String(e).slice(0, 100) })); }
  };
  const gitAction = async (w: Workspace, action: 'init' | 'commit') => {
    try {
      const r = action === 'init' ? await api.gitInit(w.path) : await api.gitCommit(w.path, t('BioDSH 快照 {time}', { time: new Date().toLocaleString() }));
      setGit((g) => ({ ...g, [w.workspaceId]: r as GitInfo }));
      toast(action === 'init' ? t('已开启版本控制') : t('已保存快照'));
    } catch (e) { toast(t('失败：{msg}', { msg: String(e).slice(0, 80) })); }
  };
  const rpc = async (method: string, payload: unknown, ok?: string) => { try { await api.dshRpc(method, payload); await refresh(); if (ok) toast(ok); } catch (e) { toast(t('失败：{msg}', { msg: String(e).slice(0, 80) })); } };
  const ask = (x: number, y: number, context: string, hint: string) => window.dispatchEvent(new CustomEvent('biodsh:ask', { detail: { x, y, context, hint } }));

  const sessionMenu = (e: React.MouseEvent, s: SessionRow, w: Workspace) => {
    e.preventDefault(); e.stopPropagation();
    const pinned = pins.includes(s.sessionId);
    setMenu({ x: e.clientX, y: e.clientY, items: [
      { label: pinned ? t('取消置顶') : t('置顶'), icon: <Pin size={13} />, onClick: () => savePins(pinned ? pins.filter((p) => p !== s.sessionId) : [s.sessionId, ...pins]) },
      { label: t('重命名'), icon: <Pencil size={13} />, onClick: () => { const v = window.prompt(t('新的任务名称'), t(sessionTitle(s))); if (v && v.trim()) void rpc('session.rename', { sessionId: s.sessionId, title: v.trim() }, t('已重命名')); } },
      { label: t('分享（导出任务记录）'), icon: <Share2 size={13} />, onClick: () => { void (api.sessionExport(s.sessionId) as Promise<string | null>).then((p) => p && toast(t('已导出到 {path}', { path: p }))).catch((err: unknown) => toast(t('导出失败：{msg}', { msg: String(err).slice(0, 80) }))); } },
      'sep',
      { label: t('归档'), icon: <Archive size={13} />, onClick: () => { void rpc('workspace.archiveSession', { sessionId: s.sessionId }, t('已归档')); if (current === s.sessionId) setCurrent(null); } },
      { label: t('永久删除'), icon: <Trash2 size={13} />, danger: true, onClick: () => { if (window.confirm(t('永久删除任务「{title}」？记录文件会从磁盘删除，无法恢复。', { title: t(sessionTitle(s)) }))) { void (api.sessionDelete(s.sessionId) as Promise<number>).then(() => { if (current === s.sessionId) setCurrent(null); return refresh(); }).then(() => toast(t('已永久删除'))).catch((err: unknown) => toast(`${t('删除失败')}: ${String(err).slice(0, 80)}`)); } } },
      'sep',
      { label: t('问一下：这个任务是什么？'), icon: <Sparkles size={13} />, onClick: () => ask(e.clientX, e.clientY, t('项目「{project}」里的任务「{session}」', { project: w.title, session: t(sessionTitle(s)) }), t('这个任务是关于什么的？')) },
    ] });
  };
  const projectMenu = (e: React.MouseEvent, w: Workspace) => {
    e.preventDefault(); e.stopPropagation();
    const g = git[w.workspaceId];
    setMenu({ x: e.clientX, y: e.clientY, items: [
      { label: t('新建任务'), icon: <Plus size={13} />, onClick: () => { void newSession(w.workspaceId); } },
      { label: t('重命名项目'), icon: <Pencil size={13} />, onClick: () => { const v = window.prompt(t('项目名称'), w.title); if (v && v.trim()) void rpc('workspace.rename', { workspaceId: w.workspaceId, title: v.trim() }, t('已重命名')); } },
      { label: t('打开文件夹'), icon: <FolderOpen size={13} />, onClick: () => { void api.openPath(w.path); } },
      'sep',
      ...(g?.available ? [g.isRepo
        ? { label: g.dirty ? t('保存版本快照（{n} 处改动）', { n: g.dirty }) : t('保存版本快照（没有改动）'), icon: <GitCommitHorizontal size={13} />, disabled: !g.dirty, onClick: () => { void gitAction(w, 'commit'); } }
        : { label: t('开启版本控制（git）'), icon: <GitBranch size={13} />, onClick: () => { void gitAction(w, 'init'); } }, 'sep' as const] : []),
      { label: t('从列表移除（不删文件）'), icon: <Trash2 size={13} />, danger: true, onClick: () => { if (window.confirm(t('把项目「{project}」从列表移除？文件夹和文件都不会删除。', { project: w.title }))) void rpc('workspace.delete', { workspaceId: w.workspaceId }, t('已移除')); } },
    ] });
  };

  const q = query.trim().toLowerCase();
  const grouped = useMemo(() => workspaces.map((w) => {
    const rows = w.sessionIds.map((id) => sessions[id]).filter((s): s is SessionRow => !!s && !archived.has(s.sessionId)).sort((a, b) => b.updatedAt - a.updatedAt);
    let blankSeen = false;
    const dedup = rows.filter((s) => { if (!s.blank) return true; if (blankSeen) return false; blankSeen = true; return true; });
    const ordered = [...dedup.filter((s) => pins.includes(s.sessionId)), ...dedup.filter((s) => !pins.includes(s.sessionId))];
    const name = (w.title || w.path).toLowerCase();
    const hit = !q || name.includes(q);
    return { w, rows: hit ? ordered : ordered.filter((s) => t(sessionTitle(s)).toLowerCase().includes(q)), hit };
  }).filter((g) => g.hit || g.rows.length > 0), [workspaces, sessions, archived, pins, q, lang]);

  const usage = useMemo(() => {
    const all = Object.values(sessions).reduce((n, s) => n + sessionTokens(s), 0);
    const cur = current && sessions[current] ? sessionTokens(sessions[current]) : 0;
    const w = workspaces.find((x) => current && x.sessionIds.includes(current));
    const proj = w ? w.sessionIds.reduce((n, id) => n + (sessions[id] ? sessionTokens(sessions[id]) : 0), 0) : 0;
    return { all, cur, proj, projName: w?.title };
  }, [sessions, workspaces, current]);

  const shownFiles = files.filter((f) => (fileTab === 'results' ? isResult(f) : !isResult(f)) && (!q || f.rel.toLowerCase().includes(q))).slice(0, 60);

  return (
    <aside className="tree" aria-label={t('项目与任务')}>
      <div className="tree-head drag">
        <div className="tree-title">
          <div className="min-w-0"><div className="eyebrow">{t('工作区')}</div><div className="serif truncate">{t('我的研究')}</div></div>
          <div className="flex no-drag">
            <button className="icon-btn" title={t('新建项目（选一个文件夹）')} aria-label={t('新建项目（选一个文件夹）')} onClick={addProject}><BioIcon name="ui-new-project" size={17} /></button>
            <button className="icon-btn" title={t('刷新')} aria-label={t('刷新')} onClick={() => refresh(true)}><BioIcon name="ui-refresh" size={16} className={refreshing ? 'bds-spin' : undefined} /></button>
          </div>
        </div>
        <label className="tree-search no-drag"><BioIcon name="ui-search" size={15} /><input id="tree-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('搜索项目、任务和文件')} />{query && <button onClick={() => setQuery('')} aria-label={t('清除')}><X size={13} /></button>}</label>
      </div>

      <div className="tree-body">
        <div className="tree-sec"><span>{t('项目')}</span><span className="acts"><button onClick={addProject}><BioIcon name="ui-new-project" size={14} />{t('新建项目')}</button></span></div>
        {dsh.state !== 'running' && <div className="empty">{dsh.state === 'starting' ? t('智能体启动中…') : t('智能体未运行')}</div>}
        {grouped.map(({ w, rows }) => {
          const g = git[w.workspaceId]; const open = !collapsed[w.workspaceId] || !!q;
          return (
            <div key={w.workspaceId} className="proj">
              <div className="proj-row" role="button" tabIndex={0} onClick={() => setCollapsed((c) => ({ ...c, [w.workspaceId]: open }))} onContextMenu={(e) => projectMenu(e, w)} title={w.path}>
                {open ? <ChevronDown size={13} style={{ color: 'var(--text-3)' }} /> : <ChevronRight size={13} style={{ color: 'var(--text-3)' }} />}
                <span className="name">{w.title || w.path.split(/[\\/]/).pop()}</span>
                {g?.isRepo && <span className="tag-mini" title={t('版本控制已开启 · 分支 {branch}', { branch: g.branch ?? '' })}><GitBranch size={9} className="inline" /> {g.dirty || ''}</span>}
                <button className="icon-btn add" title={t('在此项目新建任务')} aria-label={t('在此项目新建任务')} onClick={(e) => { e.stopPropagation(); void newSession(w.workspaceId); }}><BioIcon name="ui-new-task" size={15} /></button>
                <span className="count">{rows.length}</span>
              </div>
              {open && (
                <div className="tasks">
                  {rows.map((s) => {
                    const active = current === s.sessionId && tab === 'chat';
                    return (
                      <button key={s.sessionId} className={`task ${active ? 'active' : ''}`} onClick={() => openSession(s.sessionId)} onContextMenu={(e) => sessionMenu(e, s, w)} title={sessionTokens(s) ? `${fmtTokens(sessionTokens(s))} tokens` : undefined}>
                        {pins.includes(s.sessionId) ? <Pin size={10} style={{ color: 'var(--orange)' }} /> : <span className={`sdot ${s.running ? 'run' : s.blank ? 'blank' : 'done'}`} />}
                        <span className="t">{t(sessionTitle(s))}</span>
                        <span className="d">{s.running ? t('运行中') : fmtDay(s.updatedAt)}</span>
                      </button>
                    );
                  })}
                  <button className="newtask" onClick={() => newSession(w.workspaceId)} disabled={busy}><BioIcon name="ui-new-task" size={13} />{t('新建任务')}</button>
                </div>
              )}
            </div>
          );
        })}
        {dsh.state === 'running' && workspaces.length === 0 && <div className="empty empty-art"><BioIcon name="illustrations-empty-projects" size={180} /><span>{t('还没有项目。点「新建项目」选一个放数据的文件夹。')}</span></div>}
      </div>

      {currentWs && (
        <div className="tree-files">
          <div className="tree-sec"><span className="truncate">{t('项目文件')}</span><span className="acts"><button onClick={() => void api.openPath(currentWs.path)}><BioIcon name="ui-folder-open" size={14} />{t('打开')}</button></span></div>
          <div className="tabs-mini"><button className={fileTab === 'data' ? 'on' : ''} onClick={() => setFileTab('data')}>{t('数据')}</button><button className={fileTab === 'results' ? 'on' : ''} onClick={() => setFileTab('results')}>{t('结果')}</button></div>
          <div className="list">
            {shownFiles.map((f) => (
              <button key={f.rel} className="frow" title={f.rel} onClick={() => void api.openPath(`${currentWs.path}/${f.rel}`)}><BioIcon name={fileIconFor(f.kind, f.name)} size={16} style={{ color: 'var(--text-3)' }} /><span className="t">{f.name}</span><span className="s">{fmtSize(f.size)}</span></button>
            ))}
            {shownFiles.length === 0 && <div className="empty empty-art small">{fileTab === 'results' && !q && <BioIcon name="illustrations-empty-results" size={132} />}<span>{fileTab === 'data' ? t('把数据文件放进项目文件夹即可') : t('还没有生成结果')}</span></div>}
          </div>
        </div>
      )}

      <div className="tree-foot">
        <button className="foot-chip" onClick={() => setUsageOpen((v) => !v)} title={t('点击查看用量明细')}>
          <BioIcon name={offline ? 'ui-offline' : 'ui-balance'} size={16} />
          <span className="flex-1 truncate">{offline ? t('本地/内网模型') : balance?.total != null ? t('余额 {amount}', { amount: `${balance.currency === 'CNY' ? '¥' : '$'}${Number(balance.total).toFixed(2)}` }) : balance?.error ?? t('查询余额…')}</span>
          <span className="sdot" style={{ background: dsh.state === 'running' ? 'var(--green)' : dsh.state === 'starting' ? 'var(--orange)' : 'var(--text-3)' }} title={dsh.state === 'running' ? t('智能体运行中') : t('智能体未运行')} />
        </button>
      </div>
      {usageOpen && <UsagePanel balance={balance} usage={usage} onClose={() => setUsageOpen(false)} />}
      {notice && <div className="absolute left-3 right-3 bottom-[56px] z-[65] px-3 py-2 rounded-lg t-caption rise" style={{ background: 'var(--text)', color: 'var(--bg)' }}>{notice}</div>}
      {menu && <ContextMenu menu={menu} onClose={() => setMenu(null)} />}
    </aside>
  );
}

function UsagePanel({ balance, usage, onClose }: { balance: Balance | null; usage: { all: number; cur: number; proj: number; projName?: string }; onClose: () => void }) {
  const { pushOverlay, popOverlay } = useApp();
  const { t } = useT();
  useEffect(() => { pushOverlay(); return () => popOverlay(); }, [pushOverlay, popOverlay]);
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [onClose]);
  const sym = balance?.currency === 'CNY' ? '¥' : '$';
  const row = (l: string, v: string) => <div className="flex items-baseline justify-between gap-3"><span className="t-body" style={{ color: 'var(--text-2)' }}>{l}</span><span className="mono tnum" style={{ fontSize: 12 }}>{v}</span></div>;
  return (
    <div className="absolute left-3 right-3 bottom-[56px] z-[66] card p-3.5 flex flex-col gap-2 rise" style={{ boxShadow: 'var(--shadow-sheet)' }}>
      <div className="flex items-center justify-between"><span className="serif" style={{ fontSize: 15 }}>{t('用量与额度')}</span><button className="icon-btn" onClick={onClose}><X size={13} /></button></div>
      <div className="eyebrow">{t('DeepSeek 账户')}</div>
      {balance?.total != null ? <>{row(t('可用余额'), `${sym}${Number(balance.total).toFixed(2)}`)}{balance.granted != null && row(t('赠送'), `${sym}${Number(balance.granted).toFixed(2)}`)}{balance.topped != null && row(t('充值'), `${sym}${Number(balance.topped).toFixed(2)}`)}</> : <div className="t-body">{balance?.error ?? t('查询中…')}</div>}
      <div className="eyebrow mt-1">{t('Token 用量（含缓存命中）')}</div>
      {row(t('本任务'), fmtTokens(usage.cur))}
      {row(usage.projName ? t('本项目「{project}」', { project: usage.projName }) : t('本项目'), fmtTokens(usage.proj))}
      {row(t('全部任务'), fmtTokens(usage.all))}
    </div>
  );
}
