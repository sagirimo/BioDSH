import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ExternalLink, ThumbsUp, ThumbsDown } from 'lucide-react';
import { BioIcon, SkillIcon } from '../icons';
import { useApp } from '../store';
import Markdown from '../components/Markdown';
import type { CatalogSkill } from '@shared/types';
import { useT } from '../i18n';
import { TopBar } from '../components/Chrome';

// 技能中心：全部技能都已对智能体可用（技能精选会按任务自动挑选），这里负责浏览、搜索与查看详情。
const DOMAIN_ORDER = ['单细胞与空间', '转录组与表达', '基因组与变异', '表观与调控', '蛋白与结构', '药物与化学', '临床与医学', '微生物与免疫', '代谢与其他组学', '数据与工具'];
type Source = 'all' | 'official' | 'community';
const PAGE = 60;
const domainOf = (s: CatalogSkill) => s.domain_zh ?? '数据与工具';
// 英文模式：目录里的中文名/简介/子类没有英文版，改用英文 description 与翻译后的领域名
const skillSummary = (s: CatalogSkill, lang: string) => (lang === 'en' ? (s.description || s.summary) : s.summary);

interface Rating { vote: number }

export default function SkillsView() {
  const { catalog, skillDetail, openSkill } = useApp();
  const detail = skillDetail ? catalog.find((s) => s.id === skillDetail) : undefined;
  return detail ? <SkillDetail s={detail} onBack={() => openSkill(null)} /> : <SkillHub />;
}

function SkillCard({ s }: { s: CatalogSkill }) {
  const { openSkill } = useApp();
  const { t, lang } = useT();
  return (
    <button className="skill-card" onClick={() => openSkill(s.id)}>
      <span className="skill-head"><span className="dom-ic"><SkillIcon category={s.category} domain={domainOf(s)} size={22} /></span><h3>{s.id}</h3></span>
      <span className="eyebrow">{lang === 'en' ? t(domainOf(s)) : (s.subcategory || domainOf(s))}</span>
      <span className="desc">{skillSummary(s, lang)}</span>
      <span className="meta">{lang === 'en' ? (s.name_en ?? s.id) : s.name} · v{s.version}</span>
      <span className="foot">
        <span className="src"><BioIcon name={s.tier === 'community' ? 'ui-source-community' : 'ui-source-official'} size={13} />{s.tier === 'community' ? (s.origin?.repo ?? t('社区')) : 'BioDSH'}</span>
        <span className="pill pill-on"><BioIcon name="ui-enabled" size={12} />{t('已启用')}</span>
      </span>
    </button>
  );
}

function SkillHub() {
  const { catalog } = useApp();
  const { t } = useT();
  const [q, setQ] = useState('');
  const [source, setSource] = useState<Source>('all');
  const [domain, setDomain] = useState('all');
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [q, source, domain]);

  const counts = useMemo(() => ({ all: catalog.length, official: catalog.filter((s) => s.tier !== 'community').length, community: catalog.filter((s) => s.tier === 'community').length }), [catalog]);
  const domains = useMemo(() => { const c = new Map<string, number>(); for (const s of catalog) c.set(domainOf(s), (c.get(domainOf(s)) ?? 0) + 1); return DOMAIN_ORDER.filter((d) => c.has(d)).map((d) => [d, c.get(d)!] as const); }, [catalog]);
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return catalog.filter((s) => (source === 'all' || (source === 'official' ? s.tier !== 'community' : s.tier === 'community'))
      && (domain === 'all' || domainOf(s) === domain)
      && (!needle || [s.id, s.name, s.name_en ?? '', s.summary, s.description ?? '', s.subcategory ?? '', ...(s.tags ?? [])].some((x) => x.toLowerCase().includes(needle))));
  }, [catalog, q, source, domain]);
  const official = list.filter((s) => s.tier !== 'community');
  const community = list.filter((s) => s.tier === 'community');
  const shownCommunity = community.slice(0, page * PAGE);

  return (
    <div className="h-full flex flex-col">
      <TopBar><span className="cur">{t('技能')}</span></TopBar>
      <div className="page-scroll"><div className="page">
        <div className="page-head"><div><div className="eyebrow">Skill Hub</div><h1 className="serif">{t('技能')}</h1></div>
          <span className="t-caption" style={{ maxWidth: 360, textAlign: 'right' }}>{t('全部技能都已启用。每个任务开始时，BioDSH 会自动挑出最相关的技能交给智能体。')}</span></div>
        <label className="big-search"><BioIcon name="ui-search" size={18} /><input id="skill-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('搜索技能，例如「差异表达」「生存分析」「单细胞注释」')} /></label>
        <div className="filters">
          <span className="eyebrow" style={{ marginRight: 4 }}>{t('来源')}</span>
          {(['all', 'official', 'community'] as Source[]).map((k) => (
            <button key={k} className={`fchip ${source === k ? 'on' : ''}`} onClick={() => setSource(k)}>{k === 'all' ? t('全部') : k === 'official' ? t('BioDSH 官方') : t('社区')}<b className="tnum">{counts[k].toLocaleString()}</b></button>
          ))}
          <span className="flex-1" />
          <select id="skill-domain" className="fselect" value={domain} onChange={(e) => setDomain(e.target.value)} aria-label={t('领域')}>
            <option value="all">{t('全部领域')}</option>
            {domains.map(([d, n]) => <option key={d} value={d}>{t(d)}（{n}）</option>)}
          </select>
        </div>

        {official.length > 0 && <>
          <div className="group-h"><BioIcon name="ui-source-official" size={16} style={{ color: 'var(--accent)' }} /><span className="serif">{t('BioDSH 官方')}</span><span className="n">{t('{n} 个', { n: official.length })}</span><hr /></div>
          <div className="grid3">{official.map((s) => <SkillCard key={s.id} s={s} />)}</div>
        </>}
        {community.length > 0 && <>
          <div className="group-h" style={{ marginTop: official.length ? 30 : 6 }}><BioIcon name="ui-source-community" size={16} style={{ color: 'var(--text-3)' }} /><span className="serif">{t('社区技能')}</span><span className="n">{t('{n} 个', { n: community.length.toLocaleString() })}</span><hr /></div>
          <div className="grid3">{shownCommunity.map((s) => <SkillCard key={s.id} s={s} />)}</div>
          {shownCommunity.length < community.length && <div className="flex justify-center mt-6"><button className="btn btn-line" onClick={() => setPage((p) => p + 1)}>{t('再显示 {n} 个', { n: Math.min(PAGE, community.length - shownCommunity.length) })}</button></div>}
        </>}
        {list.length === 0 && <div className="empty empty-art"><BioIcon name="illustrations-no-search-results" size={200} /><span>{t('没有找到匹配的技能，换个关键词试试。')}</span></div>}
      </div></div>
    </div>
  );
}

function SkillDetail({ s, onBack }: { s: CatalogSkill; onBack: () => void }) {
  const { t, lang } = useT();
  const { catalog, openSkill, setTab, taskMeta } = useApp();
  const [readme, setReadme] = useState<string | null>(null);
  const [rating, setRating] = useState(0);
  useEffect(() => { setReadme(null); void (window.biodsh.skillReadme(s.id) as Promise<string>).then(setReadme).catch(() => setReadme('')); }, [s.id]);
  useEffect(() => { void (window.biodsh.ratingsGet() as Promise<Record<string, Rating>>).then((r) => setRating(r[s.id]?.vote ?? 0)); }, [s.id]);
  const rate = async (v: number) => { const next = rating === v ? 0 : v; await window.biodsh.ratingsSet(s.id, next, ''); setRating(next); };
  const related = useMemo(() => catalog.filter((x) => x.id !== s.id && x.subcategory && x.subcategory === s.subcategory).slice(0, 5), [catalog, s.id]);
  const size = readme ? new Blob([readme]).size : 0;
  const useInTask = async () => {
    if (!taskMeta) { setTab('chat'); return; }
    try { await window.biodsh.dshRpc('session.prompt', { sessionId: taskMeta.sessionId, mode: 'queue', content: [{ type: 'text', text: `/${s.id} ` + t('请按这个技能的流程处理当前项目里的数据。') }] }); setTab('chat'); } catch { setTab('chat'); }
  };

  return (
    <div className="h-full flex flex-col">
      <TopBar><button className="no-drag flex items-center gap-1.5" onClick={onBack} style={{ color: 'var(--text-2)' }}><ArrowLeft size={14} />{t('技能')}</button><span>/</span><span className="cur mono">{s.id}</span></TopBar>
      <div className="page-scroll"><div className="page">
        <div className="sd-grid">
          <div className="min-w-0">
            <span className="eyebrow">{t(domainOf(s))}{s.subcategory && lang !== 'en' ? ` · ${s.subcategory}` : ''} · {s.tier === 'community' ? t('社区') : t('BioDSH 官方')}</span>
            <div className="sd-title-row"><span className="dom-ic lg"><SkillIcon category={s.category} domain={domainOf(s)} size={24} /></span><h1 className="sd-title">{s.id}</h1></div>
            <p className="sd-lead">{skillSummary(s, lang)}</p>
            <div className="flex flex-wrap items-center gap-2">
              <button className="btn btn-primary" onClick={useInTask} title={taskMeta ? t('在当前任务「{title}」里使用', { title: taskMeta.title }) : t('先打开一个任务')}><BioIcon name="ui-run" size={14} />{t('在当前任务中使用')}</button>
              {s.origin?.url && <button className="btn btn-line" onClick={() => void window.biodsh.openExternal(s.origin!.url)}><ExternalLink size={13} />{t('来源')}</button>}
              <span className="pill pill-on"><BioIcon name="ui-enabled" size={12} />{t('已启用')}</span>
            </div>

            {(s.inputs?.length > 0 || s.outputs?.length > 0) && <>
              <div className="sd-h">{t('什么时候用')}</div>
              <div className="io2">
                <div><span className="eyebrow">{t('所需输入')}</span><ul>{s.inputs.map((x) => <li key={x.name}><code className="mono" style={{ fontSize: 12 }}>{x.name}</code>：{x.format}{x.required ? '' : t('（可选）')}</li>)}{s.inputs.length === 0 && <li>{t('见下方说明')}</li>}</ul></div>
                <div><span className="eyebrow">{t('生成的输出')}</span><ul>{s.outputs.map((x) => <li key={x}>{x}</li>)}{s.outputs.length === 0 && <li>{t('见下方说明')}</li>}</ul></div>
              </div>
            </>}

            <div className="sd-h">{t('技能说明')}</div>
            {readme === null ? <div className="t-caption">{t('读取中…')}</div> : readme ? <Markdown text={readme} /> : <div className="t-caption">{t('这个技能没有附带说明文档。')}</div>}
          </div>

          <aside className="sd-aside">
            <div className="card-flat" style={{ padding: '14px 16px' }}>
              <div className="kv">
                <span>{t('来源')}</span><span className="flex items-center gap-1.5"><BioIcon name={s.tier === 'community' ? 'ui-source-community' : 'ui-source-official'} size={13} />{s.tier === 'community' ? (s.origin?.repo ?? t('社区')) : 'BioDSH'}</span>
                <span>{t('版本')}</span><span className="mono">{s.version}</span>
                {size > 0 && <><span>{t('大小')}</span><span className="mono">{(size / 1024).toFixed(1)} KB</span></>}
                {s.origin?.license && <><span>{t('许可')}</span><span className="mono">{s.origin.license}</span></>}
                {s.level && <><span>{t('难度')}</span><span>{s.level}</span></>}
                <span>{t('离线可用')}</span><span>{s.offline ? t('是') : t('需联网')}</span>
              </div>
            </div>
            {s.tags?.length > 0 && lang !== 'en' && <div><div className="eyebrow" style={{ marginBottom: 8 }}>{t('标签')}</div><div className="flex flex-wrap gap-1.5">{s.tags.map((x) => <span key={x} className="tag-mini">{x}</span>)}</div></div>}
            {related.length > 0 && <div><div className="eyebrow" style={{ marginBottom: 8 }}>{t('相关技能')}</div><div className="flex flex-col gap-1.5">{related.map((r) => <button key={r.id} className="mono text-left truncate" style={{ fontSize: 12.5, color: 'var(--accent)' }} onClick={() => openSkill(r.id)}>{r.id}</button>)}</div></div>}
            <div><div className="eyebrow" style={{ marginBottom: 8 }}>{t('好不好用')}</div><div className="flex gap-1.5">
              <button className={`btn ${rating === 1 ? 'btn-primary' : 'btn-line'}`} onClick={() => rate(1)}><ThumbsUp size={13} />{t('好用')}</button>
              <button className={`btn ${rating === -1 ? 'btn-primary' : 'btn-line'}`} onClick={() => rate(-1)}><ThumbsDown size={13} />{t('不好用')}</button>
            </div></div>
          </aside>
        </div>
      </div></div>
    </div>
  );
}
