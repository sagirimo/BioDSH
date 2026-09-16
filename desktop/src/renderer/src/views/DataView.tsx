// 数据文件面板：工作区里有什么数据一目了然，一键让智能体分析——用户不需要记文件名。
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, FolderOpen, Sparkles, Loader2, FolderOpen as FolderBig, ClipboardList, ChevronDown } from 'lucide-react';
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
// 每种数据推荐的分析动作(概念工作台的「一键分析」):不再只一个泛按钮,给出具体、成体系的分析,
// 每条 prompt 智能体会自动挑合适的技能按其流程做。{f} = 文件相对路径。
const ANALYSES: Record<string, { label: string; prompt: string }[]> = {
  singlecell: [
    { label: '质控看数据质量', prompt: '请对工作区里的单细胞数据 {f} 做质量控制:统计细胞数/基因数、线粒体比例,画质控图,并给出建议的过滤阈值。结果存到新子文件夹。' },
    { label: '标准流程:质控→聚类→注释→出图', prompt: '请对单细胞数据 {f} 走标准流程:质控过滤、归一化、降维聚类、细胞类型注释,并输出 UMAP 与标志基因图。每步用通俗语言说明,结果存到新子文件夹。' },
    { label: '找差异基因/细胞组成差异', prompt: '请基于单细胞数据 {f} 比较分组间的细胞组成差异与差异表达基因,给出证据表和图。若分组信息不明确先问我。' },
  ],
  matrix: [
    { label: '差异表达分析', prompt: '请对表达矩阵 {f} 做差异表达分析(先确认分组),输出差异基因表、火山图和热图,结果存到新子文件夹。' },
    { label: '通路/功能富集', prompt: '请用表达矩阵 {f} 的差异基因做 KEGG/GO/GSEA 富集并作图解释,结果存到新子文件夹。' },
    { label: '聚类热图', prompt: '请对表达矩阵 {f} 做样本/基因聚类并画热图,说明分组是否清晰。' },
  ],
  table: [
    { label: '描述统计 + 概览', prompt: '请读入表格 {f},给出每列的类型与描述统计、缺失情况,并用通俗语言概括这份数据是什么。' },
    { label: '组间比较(自动选检验)', prompt: '请对表格 {f} 做组间比较:自动判断连续/分类变量并选择合适的检验(t/Mann-Whitney/卡方等),输出结果表并标注显著性。先确认分组列。' },
    { label: '相关性分析 + 作图', prompt: '请对表格 {f} 的数值变量做相关性分析并画相关热图,指出强相关的变量对。' },
    { label: '画一张图', prompt: '请根据表格 {f} 画一张最能说明问题的图(先问我想看什么关系),保存到新子文件夹。' },
  ],
  seq: [
    { label: '测序质控', prompt: '请对测序数据 {f} 做质控(FastQC 类指标),汇总质量并给出是否需要修剪的建议。' },
    { label: '比对 + 定量', prompt: '请把测序数据 {f} 比对到参考并定量(先确认物种/参考),输出计数矩阵与比对统计。' },
  ],
  figure: [ { label: '解读这张图', prompt: '请解读工作区里的图 {f}:它展示了什么、结论是什么、有没有需要注意的地方。' } ],
  report: [ { label: '解读这份结果', prompt: '请解读工作区里的结果文件 {f}:主要做了什么、核心发现、下一步建议。用通俗语言。' } ],
};
const genericAnalysis = { label: '让智能体分析', prompt: '请分析工作区里的文件 {f}:先告诉我里面是什么、质量如何,再建议下一步能做什么分析。' };
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

  const runAnalysis = async (f: FileEntry, promptTpl: string) => {
    if (dsh.state !== 'running' || !currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体分析')); setTimeout(() => setNotice(null), 4000); return; }
    setBusyRel(f.rel);
    try { await api.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text: t(promptTpl, { f: f.rel }) }] }); setTab('chat'); }
    catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
    finally { setBusyRel(null); }
  };
  // 左键「分析 ▾」弹出该数据类型的推荐分析(具体、成体系),而不是一个泛按钮
  const analysisMenu = (e: React.MouseEvent, f: FileEntry) => {
    e.preventDefault(); e.stopPropagation();
    const acts = ANALYSES[f.kind] ?? [genericAnalysis];
    setMenu({ x: e.clientX, y: e.clientY, items: [
      ...acts.map((a) => ({ label: t(a.label), icon: <SparklesIcon size={13} />, onClick: () => { void runAnalysis(f, a.prompt); } })),
      ...(ANALYSES[f.kind] ? [{ label: t(genericAnalysis.label), icon: <SparklesIcon size={13} />, onClick: () => { void runAnalysis(f, genericAnalysis.prompt); } }] : []),
    ] });
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
              <div className="flex flex-col gap-2">
                {items.map((f) => {
                  const acts = (ANALYSES[f.kind] ?? [genericAnalysis]).slice(0, 3);
                  return (
                    <div key={f.rel} className="dv-file" onContextMenu={(e) => fileMenu(e, f)}>
                      <div className="dv-file-top">
                        <FileTypeIcon type={f.kind} size={16} />
                        <div className="min-w-0 flex-1">
                          <div className="t-body truncate selectable" title={f.rel}>{f.rel}</div>
                          <div className="t-caption truncate">{fmtSize(f.size)} · {fmtTime(f.modified)}{f.preview ? ` · ${t('列')}: ${f.preview}` : ''}</div>
                        </div>
                        {busyRel === f.rel && <Loader2 size={14} className="spin shrink-0" style={{ color: 'var(--accent)' }} />}
                      </div>
                      <div className="dv-acts">
                        <span className="dv-acts-label"><Sparkles size={11} /> {t('推荐分析')}</span>
                        {acts.map((a) => <button key={a.label} className="dv-chip" disabled={busyRel === f.rel} onClick={() => runAnalysis(f, a.prompt)}>{t(a.label)}</button>)}
                        <button className="dv-chip dv-chip-more" disabled={busyRel === f.rel} onClick={(e) => analysisMenu(e, f)}>{t('更多')} <ChevronDown size={11} /></button>
                      </div>
                    </div>
                  );
                })}
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
