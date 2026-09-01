// 数据文件面板：工作区里有什么数据一目了然，一键让智能体分析——用户不需要记文件名。
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, FolderOpen, Sparkles, Loader2, FolderOpen as FolderBig, ClipboardList } from 'lucide-react';
import { FileTypeIcon } from '../icons';
import { useApp } from '../store';
import ContextMenu, { type MenuState } from '../components/ContextMenu';
import { Copy, Sparkles as SparklesIcon } from 'lucide-react';
import { useT } from '../i18n';

interface FileEntry { name: string; rel: string; size: number; modified: number; kind: string; preview?: string }

const KIND_META: Record<string, { label: string }> = {
  singlecell: { label: '单细胞数据' },
  matrix: { label: '表达矩阵' },
  table: { label: '表格' },
  figure: { label: '图' },
  seq: { label: '测序数据' },
  meta: { label: '元数据' },
  report: { label: '报告' },
  other: { label: '其他' },
};
const KIND_ORDER = ['singlecell', 'matrix', 'table', 'seq', 'figure', 'report', 'meta', 'other'];
const fmtSize = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);
const fmtTime = (s: number) => new Date(s * 1000).toLocaleString(undefined, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

function Thumb({ rel, wsPath }: { rel: string; wsPath: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => { let alive = true; void (window.biodsh.readWorkspaceImage(rel, wsPath) as Promise<string>).then((s) => alive && setSrc(s)).catch(() => alive && setSrc(null)); return () => { alive = false; }; }, [rel, wsPath]);
  if (!src) return null;
  return <img src={src} alt={rel} title={rel} className="h-[72px] rounded-lg object-cover" style={{ boxShadow: 'var(--shadow-card)' }} />;
}

function OutputCard({ dir, items, mtime, onAnalyze, busy, onMenu, wsPath }: { dir: string; items: FileEntry[]; mtime: number; onAnalyze: () => void; busy: boolean; onMenu: (e: React.MouseEvent) => void; wsPath: string }) {
  const { t } = useT();
  const { info, settings } = useApp();
  const figures = items.filter((f) => f.kind === 'figure' && !f.rel.toLowerCase().endsWith('.pdf')).slice(0, 3);
  const kinds = new Map<string, number>();
  for (const f of items) kinds.set(f.kind, (kinds.get(f.kind) ?? 0) + 1);
  const base = (wsPath || settings?.workspace || info?.paths.workspace || '') + (info?.platform === 'win32' ? '\\' : '/') + dir;
  return (
    <div className="card p-4 flex flex-col gap-2.5 rise" onContextMenu={onMenu}>
      <div className="flex items-center gap-2">
        <ClipboardList size={16} strokeWidth={1.75} />
        <span className="t-headline truncate flex-1" title={dir}>{dir}</span>
        <span className="t-caption">{fmtTime(mtime)}</span>
      </div>
      {figures.length > 0 && <div className="flex gap-2 overflow-x-auto">{figures.map((f) => <Thumb key={f.rel} rel={f.rel} wsPath={wsPath} />)}</div>}
      <div className="flex flex-wrap gap-1.5">{[...kinds.entries()].map(([k, n]) => <span key={k} className="badge inline-flex items-center gap-1"><FileTypeIcon type={k} size={12} /> {t(KIND_META[k]?.label ?? k)} {n}</span>)}</div>
      <div className="flex gap-2">
        <button className="btn btn-tint flex-1" disabled={busy} onClick={onAnalyze}>{busy ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />} {t('让智能体解读')}</button>
        <button className="btn btn-ghost" onClick={() => window.biodsh.openPath(base)}><FolderOpen size={13} /></button>
      </div>
    </div>
  );
}

export default function DataView() {
  const { t } = useT();
  const { info, settings, dsh, currentSession, setTab } = useApp();
  const api = window.biodsh;
  const [files, setFiles] = useState<FileEntry[] | null>(null);
  const [busyRel, setBusyRel] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [workspaces, setWorkspaces] = useState<{ workspaceId: string; path: string; title: string; sessionIds: string[] }[]>([]);
  const [wsPath, setWsPath] = useState<string>('');
  const workspace = wsPath || settings?.workspace || info?.paths.workspace || '';
  useEffect(() => {
    if (dsh.state !== 'running') return;
    void (api.dshRpc('workspace.list') as Promise<{ items: { workspaceId: string; path: string; title: string; sessionIds: string[] }[] }>).then((r) => {
      setWorkspaces(r.items);
      // 默认跟随当前对话所在的项目
      const cur = currentSession ? r.items.find((w) => w.sessionIds.includes(currentSession)) : undefined;
      if (cur && !wsPath) setWsPath(cur.path);
    }).catch(() => undefined);
  }, [dsh.state, currentSession]);

  const refresh = useCallback(async () => {
    try { setFiles(await api.workspaceFiles(workspace) as FileEntry[]); } catch { setFiles([]); }
  }, [workspace]);
  useEffect(() => { void refresh(); const timer = setInterval(() => { void refresh(); }, 8000); return () => clearInterval(timer); }, [refresh]);

  const analyzeOutput = async (dir: string, count: number) => {
    if (dsh.state !== 'running' || !currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体分析')); setTimeout(() => setNotice(null), 4000); return; }
    setBusyRel(`dir:${dir}`);
    try {
      await api.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text: t('请解读工作区里的结果文件夹「{dir}」（共 {n} 个文件）：这次分析做了什么、主要发现是什么、图各说明什么问题。用通俗语言讲。', { dir, n: count }) }] });
      setTab('chat');
    } catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
    finally { setBusyRel(null); }
  };

  const sendPrompt = async (text: string) => {
    if (dsh.state !== 'running' || !currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体分析')); setTimeout(() => setNotice(null), 4000); return; }
    try { await api.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text }] }); setTab('chat'); }
    catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
  };

  const analyze = async (f: FileEntry) => {
    if (dsh.state !== 'running') { setNotice(t('智能体还没运行')); return; }
    if (!currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体分析')); setTimeout(() => setNotice(null), 4000); return; }
    setBusyRel(f.rel);
    try {
      const kindLabel = t(KIND_META[f.kind]?.label ?? '文件');
      await api.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text: t('请分析工作区里的这个{kind}文件：{rel}（{size}）。先告诉我它里面是什么、质量如何，再建议下一步可以做什么分析。', { kind: kindLabel, rel: f.rel, size: fmtSize(f.size) }) }] });
      setTab('chat');
    } catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
    finally { setBusyRel(null); }
  };

  // 分析产出卡片：子文件夹里的文件按顶层目录分组（根目录散文件不算产出）
  const outputs = (() => {
    const m = new Map<string, FileEntry[]>();
    for (const f of files ?? []) { const i = f.rel.indexOf('/'); if (i > 0) { const k = f.rel.slice(0, i); m.set(k, [...(m.get(k) ?? []), f]); } }
    return [...m.entries()].map(([dir, items]) => ({ dir, items, mtime: Math.max(...items.map((x) => x.modified)) })).sort((a, b) => b.mtime - a.mtime).slice(0, 12);
  })();
  const rootFiles = (files ?? []).filter((f) => !f.rel.includes('/'));
  const sep = info?.platform === 'win32' ? '\\' : '/';
  const absPath = (rel: string) => workspace + sep + rel.replaceAll('/', sep);
  const ask = (x: number, y: number, context: string, hint: string) => window.dispatchEvent(new CustomEvent('biodsh:ask', { detail: { x, y, context, hint } }));
  const fileMenu = (e: React.MouseEvent, f: FileEntry) => {
    e.preventDefault(); e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, items: [
      { label: t('让智能体分析'), icon: <SparklesIcon size={13} />, onClick: () => { void analyze(f); } },
      { label: t('打开所在文件夹'), icon: <FolderOpen size={13} />, onClick: () => { const dir = f.rel.includes('/') ? absPath(f.rel.slice(0, f.rel.lastIndexOf('/'))) : workspace; void window.biodsh.openPath(dir); } },
      { label: t('复制文件路径'), icon: <Copy size={13} />, onClick: () => { void navigator.clipboard.writeText(absPath(f.rel)).then(() => setNotice(t('已复制'))).catch(() => undefined); setTimeout(() => setNotice(null), 2000); } },
      'sep',
      { label: t('用系统默认程序打开（Excel / 看图…）'), icon: <FolderOpen size={13} />, onClick: () => { void window.biodsh.openPath(absPath(f.rel)); } },
      { label: t('让智能体转成 Excel 表格'), icon: <SparklesIcon size={13} />, onClick: () => { void sendPrompt(t('请把工作区里的 {rel} 转换成 Excel（.xlsx）文件，保存到一个新子文件夹，并告诉我文件名。', { rel: f.rel })); } },
      { label: t('让智能体写一份 R 分析脚本'), icon: <SparklesIcon size={13} />, onClick: () => { void sendPrompt(t('请为工作区里的 {rel} 写一份可以直接在 R / RStudio 里运行的分析脚本（读入、基本统计、作图），保存为 .R 文件并解释每一段做什么。', { rel: f.rel })); } },
      { label: t('让智能体导出 SPSS / Prism 可用格式'), icon: <SparklesIcon size={13} />, onClick: () => { void sendPrompt(t('请把工作区里的 {rel} 整理成 SPSS（.sav，用 pyreadstat；如未安装请先 uv pip install pyreadstat）和 GraphPad Prism 可直接导入的宽表 CSV，各保存一份并说明列的含义。', { rel: f.rel })); } },
      'sep',
      { label: t('问一下：这类文件是什么？'), icon: <SparklesIcon size={13} />, onClick: () => ask(e.clientX, e.clientY, t('数据文件 {rel}', { rel: f.rel }), t('{name} 这种文件是什么？里面一般有什么内容？', { name: f.name })) },
    ] });
  };
  const outputMenu = (e: React.MouseEvent, dir: string, count: number) => {
    e.preventDefault(); e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, items: [
      { label: t('让智能体解读'), icon: <SparklesIcon size={13} />, onClick: () => { void analyzeOutput(dir, count); } },
      { label: t('打开文件夹'), icon: <FolderOpen size={13} />, onClick: () => { void window.biodsh.openPath(absPath(dir)); } },
      { label: t('复制文件路径'), icon: <Copy size={13} />, onClick: () => { void navigator.clipboard.writeText(absPath(dir)).then(() => setNotice(t('已复制'))).catch(() => undefined); setTimeout(() => setNotice(null), 2000); } },
    ] });
  };

  const groups = KIND_ORDER.map((k) => ({ k, items: rootFiles.filter((f) => f.kind === k) })).filter((g) => g.items.length > 0);

  return (
    <div className="h-full flex flex-col">
      <header className="drag h-[52px] flex items-center justify-between pl-5 pr-3 hairline-b" style={{ background: 'var(--bg)' }}>
        <div className="flex items-center gap-3 min-w-0">
          <span className="t-title2">{t('分析')}</span>
          {workspaces.length > 0 ? (
            <select className="field !w-auto !h-[30px] !rounded-full !pr-7 no-drag" value={workspace} onChange={(e) => setWsPath(e.target.value)}>
              {workspaces.map((w) => <option key={w.workspaceId} value={w.path}>{w.title || w.path}</option>)}
            </select>
          ) : <span className="t-caption truncate">{workspace}</span>}
        </div>
        <div className="no-drag flex items-center gap-1">
          <button className="btn btn-ghost" onClick={() => window.biodsh.openPath(workspace)}><FolderOpen size={13} /> {t('打开文件夹')}</button>
          <button className="btn btn-ghost" onClick={() => refresh()}><RefreshCw size={13} /></button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[860px] mx-auto px-8 py-6 flex flex-col gap-6">
          {notice && <div className="px-3 py-2 rounded-lg t-body rise" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>{notice}</div>}
          {files === null && <div className="t-body" style={{ color: 'var(--text-2)' }}>{t('正在扫描…')}</div>}
          {files !== null && files.length === 0 && (
            <div className="card p-8 text-center flex flex-col items-center gap-3 rise">
              <FolderBig size={40} strokeWidth={1.4} style={{ color: 'var(--text-3)' }} />
              <div className="t-title2">{t('工作区还是空的')}</div>
              <p className="t-body max-w-[420px]" style={{ color: 'var(--text-2)' }}>{t('把要分析的数据文件（h5ad、csv、fastq……）复制进工作区文件夹，这里就会显示出来，点一下就能让智能体分析。')}</p>
              <button className="btn btn-primary" onClick={() => window.biodsh.openPath(workspace)}><FolderOpen size={14} /> {t('打开工作区文件夹')}</button>
            </div>
          )}
          {outputs.length > 0 && (
            <section>
              <div className="t-headline mb-2 flex items-center gap-1.5"><ClipboardList size={16} strokeWidth={1.75} /> {t('分析产出')} <span className="t-caption">{outputs.length}</span></div>
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
                {outputs.map((o) => <OutputCard key={o.dir} dir={o.dir} items={o.items} mtime={o.mtime} onAnalyze={() => analyzeOutput(o.dir, o.items.length)} busy={busyRel === `dir:${o.dir}`} onMenu={(e) => outputMenu(e, o.dir, o.items.length)} wsPath={workspace} />)}
              </div>
            </section>
          )}
          {groups.map(({ k, items }) => (
            <section key={k}>
              <div className="t-headline mb-2 flex items-center gap-1.5"><FileTypeIcon type={k} size={16} /> {t(KIND_META[k].label)} <span className="t-caption">{items.length}</span></div>
              <div className="card divide-y" style={{ borderColor: 'var(--border)' }}>
                {items.map((f) => (
                  <div key={f.rel} className="flex items-center gap-3 px-4 py-2.5 group" onContextMenu={(e) => fileMenu(e, f)}>
                    <div className="flex-1 min-w-0">
                      <div className="t-body truncate selectable" title={f.rel}>{f.rel}</div>
                      <div className="t-caption truncate">{fmtSize(f.size)} · {fmtTime(f.modified)}{f.preview ? ` · ${t('列')}: ${f.preview}` : ''}</div>
                    </div>
                    <button className="btn btn-tint opacity-0 group-hover:opacity-100" disabled={busyRel === f.rel} onClick={() => analyze(f)}>
                      {busyRel === f.rel ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />} {t('让智能体分析')}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
          {files !== null && files.length > 0 && <p className="t-caption pb-2" style={{ color: 'var(--text-3)' }}>{t('只显示常见数据类型，最多 500 个；扫描不进隐藏目录。')}</p>}
        </div>
      </div>
      {menu && <ContextMenu menu={menu} onClose={() => setMenu(null)} />}
    </div>
  );
}
