import { useCallback, useEffect, useMemo, useState } from 'react';
import { BioIcon } from '../icons';
import { useApp } from '../store';
import { useT } from '../i18n';
import { TopBar } from '../components/Chrome';

// 工作流中心（内部仍沿用 pipeline 命名与 biodsh.pipeline/1 格式，数据无需迁移）：读取各项目 pipelines/<id>/pipeline.json（pipeline-builder 技能写出的 biodsh.pipeline/1 格式）。
// 构建、复现、换数据重跑都在任务对话里由智能体按 pipeline-builder 的引导流程完成。
interface PStep { id: string; title: string; script?: string; depends_on?: string[]; description?: string }
interface PCheck { kind: string; description: string; expected?: string; last_result?: { passed: boolean; observed?: string; at?: string } }
interface Pipeline {
  schema?: string; id?: string; name?: string; version?: string; description?: string;
  source?: { task?: string; session_id?: string; created?: string };
  inputs?: { name: string; format?: string; description?: string }[];
  params?: { name: string; default?: unknown; description?: string }[];
  outputs?: { name: string; description?: string }[];
  steps?: PStep[]; validation?: PCheck[];
  env?: { python?: string; packages?: Record<string, string> };
  runs?: { at: string; status: string; outdir?: string; note?: string }[];
}
interface Entry { project: string; dir: string; id: string; modified: number; data: Pipeline | null; error: string | null }
interface Workspace { workspaceId: string; path: string; title: string }

const projName = (ws: Workspace[], path: string) => ws.find((w) => w.path === path)?.title || path.split(/[\\/]/).pop() || path;

export default function PipelinesView() {
  const { t } = useT();
  const { dsh, taskMeta, setTab, setCurrentSession } = useApp();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [view, setView] = useState<'pipes' | 'runs'>('pipes');
  const [notice, setNotice] = useState<string | null>(null);
  const toast = (m: string) => { setNotice(m); setTimeout(() => setNotice(null), 4000); };

  const load = useCallback(async () => {
    if (dsh.state !== 'running') return;
    try {
      const ws = (await window.biodsh.dshRpc('workspace.list') as { items: Workspace[] }).items;
      setWorkspaces(ws);
      setEntries(await window.biodsh.pipelinesList(ws.map((w) => w.path)) as Entry[]);
    } catch { /* 智能体未就绪时稍后重试 */ }
  }, [dsh.state]);
  useEffect(() => { void load(); const timer = setInterval(load, 10_000); return () => clearInterval(timer); }, [load]);
  const sorted = useMemo(() => [...entries].sort((a, b) => b.modified - a.modified), [entries]);
  const cur = sorted.find((e) => e.dir === sel) ?? sorted[0];

  // 在某个项目里开一个新任务并发出指令（工作流的构建 / 复现 / 重跑都交给智能体）
  const runInProject = async (projectPath: string, text: string, ok: string) => {
    const w = workspaces.find((x) => x.path === projectPath);
    if (!w) { toast(t('找不到这个项目')); return; }
    try {
      const id = await window.biodsh.dshNewSession(w.workspaceId) as string;
      setCurrentSession(id);
      await window.biodsh.dshRpc('session.prompt', { sessionId: id, mode: 'queue', content: [{ type: 'text', text }] });
      setTab('chat'); toast(ok);
    } catch (e) { toast(t('失败：{msg}', { msg: String(e).slice(0, 80) })); }
  };
  const fromTask = async () => {
    if (!taskMeta || taskMeta.blank) { setTab('chat'); toast(t('先在左侧打开一个已完成的任务，再点标题栏的「存为工作流」')); return; }
    try {
      await window.biodsh.dshRpc('session.prompt', { sessionId: taskMeta.sessionId, mode: 'queue', content: [{ type: 'text', text: t('/pipeline-builder 请把本任务整理成一条可复现的工作流。先列出你从本任务里提取到的实际执行步骤，等我确认保留哪些、哪些参数开放给新数据，再问我要哪些验证选项，最后写入项目的 pipelines 文件夹并做一次复现验证。') }] });
      setTab('chat');
    } catch (e) { toast(t('失败：{msg}', { msg: String(e).slice(0, 80) })); }
  };
  const makeModule = async () => {
    if (!taskMeta || taskMeta.blank) { setTab('chat'); toast(t('先打开包含这个步骤的任务')); return; }
    await window.biodsh.dshRpc('session.prompt', { sessionId: taskMeta.sessionId, mode: 'queue', content: [{ type: 'text', text: t('/pipeline-builder 我只想把本任务里的某一个步骤封装成可复用模块（单步工作流）。先列出本任务的步骤让我选一个，再按流程确认参数和验证项。') }] }).catch(() => undefined);
    setTab('chat');
  };
  // 学习已有流程：用户选的脚本 / 笔记本 / 方法文本先复制进项目，再在新任务里让智能体读懂并改写成工作流
  const learnFrom = async () => {
    const project = taskMeta?.projectPath ?? workspaces[0]?.path;
    if (!project) { setTab('chat'); toast(t('先在「项目」里添加一个项目')); return; }
    try {
      const rel = await window.biodsh.workflowSourceImport(project) as string | null;
      if (!rel) return;
      await runInProject(project, t('/pipeline-builder 学习模式：请阅读 {file}（别人或以前写好的分析流程），按技能里「从已有文件学习」的步骤，先用编号清单复述它的步骤、输入、参数和输出让我确认，再改写成本项目可复现的工作流，并用我指定的数据跑一次验证。', { file: rel }), t('已复制到 {file}，正在新任务里学习', { file: rel }));
    } catch (e) { toast(t('失败：{msg}', { msg: String(e).slice(0, 80) })); }
  };
  const reproduce = (e: Entry) => runInProject(e.project, t('/pipeline-builder 请对 pipelines/{id} 做一次复现验证：在新的输出目录里执行 run.py，逐项运行 pipeline.json 里的验证项，把结果写回 validation 和 runs，并如实报告差异。', { id: e.id }), t('已在新任务里开始复现验证'));
  const runNew = (e: Entry) => runInProject(e.project, t('/pipeline-builder 我要用新数据运行 pipelines/{id}。先告诉我它需要哪些输入和参数，等我指定新数据后，在新的输出目录里运行 run.py 并汇报结果。', { id: e.id }), t('已在新任务里准备运行'));

  const allRuns = useMemo(() => sorted.flatMap((e) => (e.data?.runs ?? []).map((r) => ({ ...r, name: e.data?.name ?? e.id, project: projName(workspaces, e.project) }))).sort((a, b) => b.at.localeCompare(a.at)), [sorted, workspaces]);

  return (
    <div className="h-full flex flex-col">
      <TopBar actions={<>{notice && <span className="pill pill-on rise">{notice}</span>}<button className="icon-btn" title={t('刷新')} aria-label={t('刷新')} onClick={() => void load()}><BioIcon name="ui-refresh" size={16} /></button></>}><span className="cur">{t('工作流')}</span></TopBar>
      <div className="page-scroll"><div className="page">
        <div className="page-head"><div><div className="eyebrow">{t('工作流中心')}</div><h1 className="serif">{t('工作流')}</h1></div></div>
        <div className="tabbar"><button className={view === 'pipes' ? 'on' : ''} onClick={() => setView('pipes')}>{t('工作流')}</button><button className={view === 'runs' ? 'on' : ''} onClick={() => setView('runs')}>{t('运行记录')}</button></div>

        {view === 'pipes' && <>
          <section className="custom-box">
            <div className="top">
              <div><h2>{t('自定义工作流')}</h2><p>{t('把已完成的任务整理成可复现的工作流：你逐步确认保留的步骤、开放的参数和验证项，之后可以换数据重跑。')}</p></div>
              <button className="btn btn-primary" onClick={fromTask}><BioIcon name="ui-save-workflow" size={15} />{t('构建自定义工作流')}</button>
            </div>
            <div className="opts4">
              <button className="opt-card" onClick={fromTask}><BioIcon name="ui-save-workflow" size={20} className="opt-ic" /><h3>{t('从已完成任务开始')}<span className="tag-mini">{t('推荐')}</span></h3><p>{t('选一个任务，提取它真正执行过的步骤、参数和输入输出。')}</p><span className="go">{t('用当前任务开始 →')}</span></button>
              <button className="opt-card" onClick={makeModule}><BioIcon name="ui-workflows" size={20} className="opt-ic" /><h3>{t('封装为可复用模块')}</h3><p>{t('把一个步骤（例如质控过滤）单独保存，供多条工作流共用。')}</p><span className="go">{t('选择步骤 →')}</span></button>
              <button className="opt-card" onClick={learnFrom} disabled={dsh.state !== 'running'}><BioIcon name="ui-learn-workflow" size={20} className="opt-ic" /><h3>{t('学习已有流程')}</h3><p>{t('选一个别人或以前写好的脚本、笔记本或方法说明，智能体读懂后改写成你项目里可复现的工作流。')}</p><span className="go">{t('选择文件 →')}</span></button>
              <button className="opt-card" onClick={() => cur && reproduce(cur)} disabled={!cur}><BioIcon name="ui-reproduce" size={20} className="opt-ic" /><h3>{t('复现验证')}</h3><p>{t('用原始数据在干净的输出目录里重跑，逐项核对输出是否与原任务一致。')}</p><span className="go">{cur ? t('验证「{name}」→', { name: cur.data?.name ?? cur.id }) : t('还没有工作流')}</span></button>
            </div>
          </section>

          {sorted.length === 0 ? (
            <div className="empty empty-art" style={{ marginTop: 24 }}><BioIcon name="illustrations-empty-workflows" size={220} /><span>{t('还没有工作流。打开一个已完成的任务，点标题栏的「存为工作流」，按对话里的提示确认步骤即可。')}</span></div>
          ) : (
            <div className="md2">
              <div className="flex flex-col gap-2.5">
                {sorted.map((e) => {
                  const p = e.data; const failed = p?.validation?.filter((v) => v.last_result && !v.last_result.passed).length ?? 0;
                  return (
                    <button key={e.dir} className={`p-item ${cur?.dir === e.dir ? 'on' : ''}`} onClick={() => setSel(e.dir)}>
                      <h3>{p?.name ?? e.id}</h3>
                      <p>{e.error ? t('pipeline.json 无法解析：{msg}', { msg: e.error.slice(0, 60) }) : p?.description}</p>
                      <span className="m"><span>{projName(workspaces, e.project)}</span>{p?.version && <span>v{p.version}</span>}<span>{t('{n} 个步骤', { n: p?.steps?.length ?? 0 })}</span>{failed > 0 && <span style={{ color: 'var(--orange)' }}>{t('{n} 项验证未通过', { n: failed })}</span>}</span>
                    </button>
                  );
                })}
              </div>
              {cur && <PipelineDetail e={cur} project={projName(workspaces, cur.project)} onRun={() => runNew(cur)} onReproduce={() => reproduce(cur)} />}
            </div>
          )}
        </>}

        {view === 'runs' && (allRuns.length === 0 ? <div className="empty">{t('还没有运行记录')}</div> : (
          <div style={{ overflowX: 'auto', borderRadius: 12, boxShadow: '0 0 0 1px var(--border)' }} className="md">
            <table><thead><tr><th>{t('时间')}</th><th>{t('工作流')}</th><th>{t('项目')}</th><th>{t('状态')}</th><th>{t('说明')}</th></tr></thead>
              <tbody>{allRuns.map((r, i) => <tr key={i}><td className="mono">{r.at.replace('T', ' ').slice(0, 16)}</td><td>{r.name}</td><td>{r.project}</td><td><span className={`pill ${r.status === 'passed' ? 'pill-on' : 'pill-warn'}`}>{r.status === 'passed' ? t('通过') : r.status}</span></td><td>{r.note}</td></tr>)}</tbody></table>
          </div>
        ))}
      </div></div>
    </div>
  );
}

function PipelineDetail({ e, project, onRun, onReproduce }: { e: Entry; project: string; onRun: () => void; onReproduce: () => void }) {
  const { t } = useT();
  const p = e.data ?? {};
  const lastRun = p.runs?.[p.runs.length - 1];
  return (
    <article className="p-detail">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><h2 className="serif" style={{ fontSize: 25, margin: 0 }}>{p.name ?? e.id}</h2>
          <div className="t-caption" style={{ marginTop: 4, fontSize: 12.5 }}>{[p.version && t('版本 {v}', { v: p.version }), project, p.source?.task && t('来自任务「{task}」', { task: p.source.task }), lastRun && t('最近运行 {at}', { at: lastRun.at.slice(0, 10) })].filter(Boolean).join(' · ')}</div></div>
        <div className="flex gap-1.5"><button className="btn btn-line" onClick={() => void window.biodsh.openPath(e.dir)}><BioIcon name="ui-folder-open" size={14} />{t('文件夹')}</button><button className="btn btn-line" onClick={onReproduce}><BioIcon name="ui-reproduce" size={14} />{t('复现验证')}</button><button className="btn btn-primary" onClick={onRun}><BioIcon name="ui-run" size={14} />{t('用新数据运行')}</button></div>
      </div>
      {p.description && <p style={{ color: 'var(--text-2)', margin: '12px 0 0' }}>{p.description}</p>}

      <div className="io2" style={{ marginTop: 16 }}>
        <div><span className="eyebrow">{t('所需输入')}</span><ul>{(p.inputs ?? []).map((x) => <li key={x.name}><code className="mono" style={{ fontSize: 12 }}>{x.name}</code>{x.format ? `（${x.format}）` : ''}{x.description ? `：${x.description}` : ''}</li>)}</ul></div>
        <div><span className="eyebrow">{t('生成的输出')}</span><ul>{(p.outputs ?? []).map((x) => <li key={x.name}><code className="mono" style={{ fontSize: 12 }}>{x.name}</code>{x.description ? `：${x.description}` : ''}</li>)}</ul></div>
      </div>

      {(p.params?.length ?? 0) > 0 && <>
        <div className="sd-h" style={{ fontSize: 16 }}>{t('可调参数')}</div>
        <div className="md" style={{ overflowX: 'auto', borderRadius: 10, boxShadow: '0 0 0 1px var(--border)' }}><table><thead><tr><th>{t('参数')}</th><th>{t('默认')}</th><th>{t('说明')}</th></tr></thead><tbody>{p.params!.map((x) => <tr key={x.name}><td><code>{x.name}</code></td><td><code>{JSON.stringify(x.default)}</code></td><td>{x.description}</td></tr>)}</tbody></table></div>
      </>}

      {(p.validation?.length ?? 0) > 0 && <>
        <div className="sd-h" style={{ fontSize: 16 }}>{t('验证项')}</div>
        {p.validation!.map((v, i) => (
          <div key={i} className="check-row">
            {!v.last_result ? <BioIcon name="ui-pending" size={16} label={t('未运行')} style={{ color: 'var(--text-3)', marginTop: 2 }} /> : v.last_result.passed ? <BioIcon name="ui-check" size={16} label={t('通过')} style={{ color: 'var(--green)', marginTop: 2 }} /> : <BioIcon name="ui-cross" size={16} label={t('未通过')} style={{ color: 'var(--red)', marginTop: 2 }} />}
            <span>{v.description}</span>
            <span className="r">{v.last_result ? `${v.last_result.observed ?? ''}${v.expected ? ` / ${v.expected}` : ''}` : t('未运行')}</span>
          </div>
        ))}
      </>}

      {(p.steps?.length ?? 0) > 0 && <>
        <div className="sd-h" style={{ fontSize: 16 }}>{t('工作流拓扑')}</div>
        <Dag steps={p.steps!} />
      </>}
      {p.env?.packages && <div className="t-caption mono" style={{ marginTop: 14 }}>{[p.env.python && `python ${p.env.python}`, ...Object.entries(p.env.packages).map(([k, v]) => `${k} ${v}`)].filter(Boolean).join(' · ')}</div>}
    </article>
  );
}

// 按依赖分层排版：列 = 到根的最长路径，行 = 层内序号。
function Dag({ steps }: { steps: PStep[] }) {
  const { t } = useT();
  const W = 132, H = 40, GX = 34, GY = 16;
  const depth = new Map<string, number>();
  const byId = new Map(steps.map((s) => [s.id, s]));
  const d = (id: string, seen = new Set<string>()): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (seen.has(id)) return 0; seen.add(id);
    const deps = (byId.get(id)?.depends_on ?? []).filter((x) => byId.has(x));
    const v = deps.length ? Math.max(...deps.map((x) => d(x, seen))) + 1 : 0;
    depth.set(id, v); return v;
  };
  steps.forEach((s) => d(s.id));
  const cols = new Map<number, string[]>();
  steps.forEach((s) => { const c = depth.get(s.id)!; cols.set(c, [...(cols.get(c) ?? []), s.id]); });
  const maxRows = Math.max(...[...cols.values()].map((v) => v.length));
  const pos = new Map<string, { x: number; y: number }>();
  for (const [c, ids] of cols) ids.forEach((id, r) => pos.set(id, { x: 4 + c * (W + GX), y: 4 + (r + (maxRows - ids.length) / 2) * (H + GY) }));
  const width = 8 + (Math.max(...cols.keys()) + 1) * (W + GX) - GX;
  const height = 8 + maxRows * (H + GY) - GY;
  const label = (s: PStep) => (s.title.length > 9 ? `${s.title.slice(0, 8)}…` : s.title);
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={t('工作流拓扑')} style={{ maxWidth: '100%', height: 'auto' }}>
        {steps.flatMap((s) => (s.depends_on ?? []).filter((x) => pos.has(x)).map((x) => {
          const a = pos.get(x)!, b = pos.get(s.id)!; const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
          return <path key={`${x}-${s.id}`} d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`} fill="none" stroke="var(--text-3)" strokeWidth={1.2} />;
        }))}
        {steps.map((s) => { const p = pos.get(s.id)!; return (
          <g key={s.id}><title>{s.description ?? s.title}</title>
            <rect x={p.x} y={p.y} width={W} height={H} rx={10} fill="var(--surface)" stroke="var(--line)" />
            <text x={p.x + W / 2} y={p.y + H / 2 + 4.5} textAnchor="middle" fontSize={12.5} fill="var(--text)">{label(s)}</text>
          </g>
        ); })}
      </svg>
    </div>
  );
}
