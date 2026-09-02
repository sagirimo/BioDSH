import { useEffect, useMemo, useState } from 'react';
import { DomainIcon, SkillIcon } from '../icons';
import { Search, ShieldCheck, WifiOff, RotateCcw, X, FolderOpen, Trash2, ExternalLink, Sparkles, Users, Download, ThumbsUp, ThumbsDown, LayoutGrid, Award } from 'lucide-react';
import { useApp } from '../store';
import InstallButton from '../components/InstallButton';
import Markdown from '../components/Markdown';
import type { CatalogSkill } from '@shared/types';
import { useT } from '../i18n';

const PAGE = 48;
const DOMAIN_ORDER = ['单细胞与空间', '转录组与表达', '基因组与变异', '表观与调控', '蛋白与结构', '药物与化学', '临床与医学', '微生物与免疫', '代谢与其他组学', '数据与工具'];
type Tier = 'official' | 'community' | 'installed';
// 英文模式下社区技能显示英文原名与原简介；官方技能保持 name/summary。
const skillName = (s: CatalogSkill, lang: string) => (lang === 'en' && s.tier === 'community' ? (s.name_en ?? s.name) : s.name);
const skillSummary = (s: CatalogSkill, lang: string) => (lang === 'en' && s.tier === 'community' ? (s.description || s.summary) : s.summary);

interface Rating { vote: number; comment?: string; at?: number }
let ratingsCache: Record<string, Rating> = {};

export default function StoreView() {
  const { catalog, statuses, env, setTab } = useApp();
  const { t, lang } = useT();
  const [q, setQ] = useState('');
  const [tier, setTier] = useState<Tier>(() => { try { const t = localStorage.getItem('biodsh.storeTier'); localStorage.removeItem('biodsh.storeTier'); return (t as Tier) || 'official'; } catch { return 'official'; } });
  const [domain, setDomain] = useState('all');
  const [sub, setSub] = useState('all');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<CatalogSkill | null>(null);
  const [scoreInfo, setScoreInfo] = useState(false);
  const [ratings, setRatings] = useState<Record<string, Rating>>(ratingsCache);
  useEffect(() => { void (window.biodsh.ratingsGet() as Promise<Record<string, Rating>>).then((r) => { ratingsCache = r; setRatings(r); }); }, []);
  const rate = async (id: string, vote: number) => { const cur = ratings[id]?.vote ?? 0; const next = cur === vote ? 0 : vote; const all = await window.biodsh.ratingsSet(id, next, '') as Record<string, Rating>; ratingsCache = all; setRatings({ ...all }); };
  useEffect(() => { setPage(1); }, [q, tier, domain, sub]);
  useEffect(() => { setSub('all'); }, [domain, tier]);
  useEffect(() => { const h = (e: Event) => setTier((e as CustomEvent).detail as Tier); window.addEventListener('biodsh:tier', h); return () => window.removeEventListener('biodsh:tier', h); }, []);

  const pool = useMemo(() => catalog.filter((s) => {
    if (tier === 'installed') { const st = statuses[s.id]?.state; return st === 'installed' || st === 'update_available'; }
    return (s.tier ?? 'official') === tier;
  }), [catalog, statuses, tier]);
  const domains = useMemo(() => {
    const c = new Map<string, number>();
    for (const s of pool) { const d = s.domain_zh ?? '数据与工具'; c.set(d, (c.get(d) ?? 0) + 1); }
    return DOMAIN_ORDER.filter((d) => c.has(d)).map((d) => [d, c.get(d)!] as const);
  }, [pool]);
  const inDomain = useMemo(() => domain === 'all' ? pool : pool.filter((s) => (s.domain_zh ?? '数据与工具') === domain), [pool, domain]);
  const subs = useMemo(() => {
    const c = new Map<string, number>();
    for (const s of inDomain) if (s.subcategory) c.set(s.subcategory, (c.get(s.subcategory) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [inDomain]);
  const list = useMemo(() => inDomain.filter((s) => {
    if (sub !== 'all' && s.subcategory !== sub) return false;
    if (!q.trim()) return true;
    const needle = q.toLowerCase();
    return [s.name, s.name_en ?? '', s.summary, s.description ?? '', s.id, s.subcategory ?? '', ...s.tags].some((x) => x.toLowerCase().includes(needle));
  }).sort((a, b) => (b.score ?? -1) - (a.score ?? -1)), [inDomain, sub, q]); // 有评分的排前(按分降序),未评测的保持原序在后
  const shown = list.slice(0, page * PAGE);
  const [batchBusy, setBatchBusy] = useState(false);
  const { install: installOne } = useApp();
  const installAll = async (items: CatalogSkill[]) => {
    const todo = items.filter((s) => (statuses[s.id]?.state ?? 'not_installed') !== 'installed');
    if (todo.length === 0 || !window.confirm(t('安装当前列表中的 {n} 个技能？', { n: todo.length }))) return;
    setBatchBusy(true);
    try { for (const s of todo) await installOne(s.id); } finally { setBatchBusy(false); }
  };
  const featuredCommunity = catalog.filter((s) => s.tier === 'community' && s.featured);
  const featured = catalog.filter((s) => s.featured);
  const installedCount = Object.values(statuses).filter((s) => s.state === 'installed' || s.state === 'update_available').length;
  const communityCount = catalog.filter((s) => s.tier === 'community').length;

  return (
    <div className="h-full flex flex-col">
      <header className="drag h-[52px] flex items-center justify-between pl-5 hairline-b" style={{ background: 'var(--bg)' }}>
        <div className="flex items-center gap-4">
          <span className="t-title2">{t('技能商店')}</span>
          <div className="seg no-drag">
            <button className={tier === 'official' ? 'active' : ''} onClick={() => setTier('official')}><span className="inline-flex items-center gap-1"><Sparkles size={12} /> {t('官方精选')}</span></button>
            <button className={tier === 'community' ? 'active' : ''} onClick={() => setTier('community')}><span className="inline-flex items-center gap-1"><Users size={12} /> {t('社区收编')} <span className="opacity-60">{communityCount}</span></span></button>
            <button className={tier === 'installed' ? 'active' : ''} onClick={() => setTier('installed')}><span className="inline-flex items-center gap-1"><Download size={12} /> {t('已安装')} {installedCount > 0 && <span className="opacity-60">{installedCount}</span>}</span></button>
          </div>
        </div>
        <div className="flex items-center gap-3 no-drag">
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-3)' }} />
            <input className="field !h-[30px] !pl-8 w-[240px] !rounded-full" placeholder={t('搜索 2,000+ 技能')} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          
        </div>
      </header>

      <div className="flex-1 min-h-0 flex">
        {/* 左侧分类栏 */}
        <nav className="w-[196px] shrink-0 overflow-y-auto py-3 px-2 hairline-r" style={{ background: 'var(--surface-2)', borderRight: '0.5px solid var(--border)' }}>
          <button className={`cat-item ${domain === 'all' ? 'active' : ''}`} onClick={() => setDomain('all')}><span className="w-5 flex items-center justify-center"><LayoutGrid size={15} strokeWidth={1.75} /></span><span className="flex-1">{t('全部')}</span><span className="cat-count">{pool.length}</span></button>
          <div className="t-caption px-3 pt-3 pb-1" style={{ color: 'var(--text-3)' }}>{t('领域')}</div>
          {domains.map(([d, n]) => (
            <button key={d} className={`cat-item ${domain === d ? 'active' : ''}`} onClick={() => setDomain(d)}><span className="w-5 flex items-center justify-center"><DomainIcon domain={d} size={15} /></span><span className="flex-1 truncate">{t(d)}</span><span className="cat-count">{n}</span></button>
          ))}
        </nav>

        <div className="flex-1 min-w-0 overflow-y-auto">
          <div className="max-w-[1100px] mx-auto px-7 py-5 flex flex-col gap-5">
            {!env.ready && tier !== 'installed' && (
              <div className="rounded-2xl px-5 py-3.5 flex items-center gap-4" style={{ background: 'var(--accent-soft)' }}>
                <div className="flex-1">
                  <div className="t-headline">{t('先准备一次分析环境')}</div>
                  <div className="t-body" style={{ color: 'var(--text-2)' }}>{t('技能要靠 Python 分析软件包才能运行。只需安装一次，大约几分钟。')}</div>
                </div>
                <button className="btn btn-primary" onClick={() => setTab('env')}>{t('去安装')}</button>
              </div>
            )}

            {tier === 'official' && domain === 'all' && !q && featured.length > 0 && <Hero skill={featured[0]} onOpen={() => setOpen(featured[0])} />}
            {tier === 'official' && domain === 'all' && !q && featuredCommunity.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-2"><div className="t-headline">{t('精选推荐（来自社区，按领域挑选）')} <span className="t-caption">{featuredCommunity.length}</span></div><button className="btn btn-fill !h-[26px]" disabled={batchBusy} onClick={() => installAll(featuredCommunity)}>{t('一键安装精选')}</button></div>
                <section className="grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
                  {featuredCommunity.map((s) => <SkillCard key={s.id} skill={s} onOpen={() => setOpen(s)} />)}
                </section>
              </section>
            )}

            <div className="flex items-center justify-between gap-3">
              <div className="flex flex-wrap gap-1.5 min-w-0">
                {subs.length > 1 && domain !== 'all' && (
                  <>
                    <button className={`chip ${sub === 'all' ? 'active' : ''}`} onClick={() => setSub('all')}>{t('全部小类')}</button>
                    {subs.map(([s, n]) => <button key={s} className={`chip ${sub === s ? 'active' : ''}`} onClick={() => setSub(s)}>{s} <span className="opacity-50">{n}</span></button>)}
                  </>
                )}
              </div>
              {domain === 'all' && tier !== 'installed' && <span className="t-caption">{t('左侧选一个领域，再按小类筛选')}</span>}
              <span className="flex items-center gap-2 shrink-0">
                <button className="btn btn-ghost !h-[26px] !px-2" onClick={() => setScoreInfo(true)} title={t('评分说明')}><Award size={13} /> {t('评分说明')}</button>
                {list.length > 0 && tier !== 'installed' && <button className="btn btn-fill !h-[26px]" disabled={batchBusy} onClick={() => installAll(list)}>{batchBusy ? t('批量安装中…') : t('安装本列表全部（{n}）', { n: list.filter((s) => (statuses[s.id]?.state ?? 'not_installed') !== 'installed').length })}</button>}
                <span className="t-caption shrink-0">{t('{n} 个', { n: list.length })}{tier === 'community' ? ` · ${t('来自开源社区，未经 BioDSH 评测')}` : tier === 'official' ? ` · ${t('离线、可复现、已评测')}` : ''}</span>
              </span>
            </div>

            {list.length === 0 ? (
              <div className="py-16 text-center t-body" style={{ color: 'var(--text-2)' }}>{tier === 'installed' ? t('还没有安装任何技能，去「官方精选」或「社区收编」挑一个吧') : t('没有匹配的技能')}</div>
            ) : (
              <>
                <section className="grid gap-3.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
                  {shown.map((s) => <SkillCard key={s.id} skill={s} onOpen={() => setOpen(s)} />)}
                </section>
                {shown.length < list.length && (
                  <div className="flex justify-center pt-1"><button className="btn btn-fill" onClick={() => setPage((p) => p + 1)}>{t('显示更多（还有 {n} 个）', { n: list.length - shown.length })}</button></div>
                )}
              </>
            )}
            <p className="t-caption pb-2" style={{ color: 'var(--text-3)' }}>{t('技能安装到 ~/BioDSH/dsh-home/skills，智能体会自动看到；卸载即删除该文件夹。官方技能的分数来自 BioDSH 评测记录；社区技能的中文标题与简介由模型生成，以来源仓库原文为准。')}</p>
          </div>
        </div>
      </div>

      {open && <DetailSheet skill={open} onClose={() => setOpen(null)} rating={ratings[open.id]} onRate={(v) => rate(open.id, v)} />}
      {scoreInfo && <ScoreInfoModal onClose={() => setScoreInfo(false)} />}
    </div>
  );
}

// 评分说明弹窗：讲清五维权重、用到/计划接入的公认 benchmark、以及诚实边界。
function ScoreInfoModal({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  useEffect(() => { const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [onClose]);
  const dims: [string, string, string][] = [
    ['正确性', '45%', '在公认 benchmark 或内部自动评测上的表现'],
    ['鲁棒性', '15%', '换数据集 / 随机种子，结果稳不稳'],
    ['可复现', '15%', '锁定依赖、重跑结果一致'],
    ['离线', '15%', '能否不联网、不依赖付费接口运行'],
    ['效率', '10%', '运行时间 / 内存开销'],
  ];
  const benches: [string, string][] = [
    ['单细胞', 'scIB · ARI / NMI · Azimuth'],
    ['基因调控 / 虚拟敲除', 'BEELINE (AUPRC/EPR) · scPerturb · CellOracle'],
    ['分子对接 / 虚拟筛选', 'DUD-E · LIT-PCBA · CASF-2016 (EF/AUROC/pose)'],
    ['生信 Agent', 'BixBench · LAB-Bench · ScienceAgentBench'],
    ['分子动力学', 'RMSD / RMSF 稳定性 · B-factor 相关性'],
  ];
  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="sheet" style={{ maxWidth: 560 }}>
        <div className="px-6 pt-6 pb-4 flex items-start gap-3 hairline-b">
          <span className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}><Award size={18} /></span>
          <div className="flex-1"><div className="t-title1">{t('技能评分是怎么来的')}</div><div className="t-caption mt-1">{t('一个 0–100 的综合分，让你一眼看出哪个技能更可靠')}</div></div>
          <button className="btn btn-ghost !h-6 !px-2" onClick={onClose}><X size={14} /></button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 flex flex-col gap-5">
          <div>
            <div className="t-headline mb-2">{t('五个维度加权')}</div>
            <div className="flex flex-col gap-1.5">
              {dims.map(([n, w, d]) => (
                <div key={n} className="flex items-baseline gap-2 t-body" style={{ fontSize: 13.5 }}>
                  <span style={{ width: 52 }} className="shrink-0 font-medium">{t(n)}</span>
                  <span className="badge badge-blue shrink-0">{w}</span>
                  <span style={{ color: 'var(--text-2)' }}>{t(d)}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="t-headline mb-2">{t('用到 / 计划接入的公认 benchmark')}</div>
            <div className="flex flex-col gap-1.5">
              {benches.map(([k, v]) => (
                <div key={k} className="t-body" style={{ fontSize: 13.5 }}><span className="font-medium">{t(k)}</span><span style={{ color: 'var(--text-2)' }}> — {v}</span></div>
              ))}
            </div>
          </div>
          <div className="rounded-xl p-4 t-body" style={{ background: 'var(--surface-2)', fontSize: 13, lineHeight: '20px', color: 'var(--text-2)' }}>
            {t('诚实说明：目前官方技能的分数来自 BioDSH 内部自动评测（自建 grader，全部通过），上面的公认 benchmark 正在逐步接入以给出可对外的分数。没跑过评测的技能一律标「未评测」，我们不臆造分数。')}
          </div>
        </div>
      </div>
    </>
  );
}

function Icon({ skill, size = 44 }: { skill: CatalogSkill; size?: number }) {
  return (
    <div className="flex items-center justify-center shrink-0" style={{ width: size, height: size, borderRadius: size * 0.23, background: 'var(--surface-2)', color: 'var(--accent)', boxShadow: 'inset 0 0 0 0.5px var(--border)' }}><SkillIcon category={skill.category} domain={skill.domain_zh} size={Math.round(size * 0.5)} /></div>
  );
}

function Hero({ skill, onOpen }: { skill: CatalogSkill; onOpen: () => void }) {
  const { t, lang } = useT();
  return (
    <div className="card card-hover p-6 flex items-center gap-6 rise" onClick={onOpen} style={{ background: 'linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%)' }}>
      <Icon skill={skill} size={80} />
      <div className="flex-1 min-w-0">
        <div className="t-caption uppercase tracking-wide" style={{ color: 'var(--accent)' }}>{t('精选 · 已在真实数据集验证')}</div>
        <div className="t-title1 mt-1">{skillName(skill, lang)}</div>
        <div className="t-body mt-1.5 max-w-[560px]" style={{ color: 'var(--text-2)' }}>{skillSummary(skill, lang)}</div>
        <div className="flex gap-1.5 mt-3"><Badges skill={skill} /></div>
      </div>
      <div onClick={(e) => e.stopPropagation()}><InstallButton skill={skill} size="lg" /></div>
    </div>
  );
}

function Badges({ skill }: { skill: CatalogSkill }) {
  const { t } = useT();
  if (skill.tier === 'community') {
    return (
      <>
        {skill.subcategory && <span className="badge badge-blue">{skill.subcategory}</span>}
        {skill.level && <span className="badge">{skill.level}</span>}
        {skill.has_scripts ? <span className="badge">{t('含脚本')}</span> : <span className="badge">{t('说明书型')}</span>}
      </>
    );
  }
  return (
    <>
      {typeof skill.score === 'number' && <span className="badge badge-blue" title={skill.score_source ?? t('内部评测')}><Award size={11} /> {t('评分')} {skill.score}</span>}
      {skill.offline && <span className="badge badge-green"><WifiOff size={11} /> {t('离线')}</span>}
      {skill.evidence?.reproducible && <span className="badge badge-green"><RotateCcw size={11} /> {t('可复现')}</span>}
      {skill.evidence?.tests && <span className="badge badge-blue"><ShieldCheck size={11} /> {t('评测')} {skill.evidence.tests}</span>}
      {!skill.mutates_input && <span className="badge">{t('不改动原始数据')}</span>}
    </>
  );
}

function SkillCard({ skill, onOpen }: { skill: CatalogSkill; onOpen: () => void }) {
  const { statuses } = useApp();
  const { t, lang } = useT();
  const st = statuses[skill.id]?.state;
  return (
    <div className="card card-hover p-4 flex flex-col gap-2.5 rise" onClick={onOpen}>
      <div className="flex items-start gap-3">
        <Icon skill={skill} size={40} />
        <div className="flex-1 min-w-0">
          <div className="t-headline truncate" title={skillName(skill, lang)}>{skillName(skill, lang)}</div>
          <div className="t-caption truncate">{skill.tier === 'community' ? skill.origin?.repo : `v${skill.version}`}{st === 'installed' ? ` · ${t('已安装')}` : ''}</div>
        </div>
        <div onClick={(e) => e.stopPropagation()}><InstallButton skill={skill} /></div>
      </div>
      <div className="t-body" style={{ color: 'var(--text-2)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 54 }}>{skillSummary(skill, lang)}</div>
      <div className="flex flex-wrap gap-1.5"><Badges skill={skill} /></div>
    </div>
  );
}

function DetailSheet({ skill, onClose, rating, onRate }: { skill: CatalogSkill; onClose: () => void; rating?: Rating; onRate: (v: number) => void }) {
  const { statuses, uninstall, info } = useApp();
  const { t, lang } = useT();
  const [tab, setTab] = useState<'overview' | 'io' | 'doc'>('overview');
  const [doc, setDoc] = useState('');
  useEffect(() => { void window.biodsh.skillReadme(skill.id).then(setDoc); }, [skill.id]);
  useEffect(() => { const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [onClose]);
  const st = statuses[skill.id];
  const installed = st?.state === 'installed' || st?.state === 'update_available';
  const dir = info ? `${info.paths.skills}/${skill.id}` : '';
  const community = skill.tier === 'community';
  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="sheet">
        <div className="px-6 pt-6 pb-4 flex items-start gap-4 hairline-b">
          <Icon skill={skill} size={64} />
          <div className="flex-1 min-w-0">
            <div className="t-title1 truncate">{skillName(skill, lang)}</div>
            <div className="t-caption mt-1 truncate">{community ? `${t('社区')} · ${skill.origin?.repo}` : t('BioDSH 官方')} · {skill.id}{st?.installedVersion ? ` · ${t('已安装 v{v}', { v: st.installedVersion })}` : ''}</div>
            <div className="flex flex-wrap gap-1.5 mt-3"><Badges skill={skill} /></div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <InstallButton skill={skill} />
            <button className="btn btn-ghost !h-6 !px-2" onClick={onClose}><X size={14} /></button>
          </div>
        </div>
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="seg">
            {(['overview', 'io', 'doc'] as const).map((k) => <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{t({ overview: '概览', io: '输入 / 输出', doc: '原文说明书' }[k])}</button>)}
          </div>
          {installed && (
            <div className="flex gap-1 items-center">
              <span className="t-caption mr-1">{t('好用吗？')}</span>
              <button className="btn btn-ghost !px-2" title={t('好用')} style={{ color: rating?.vote === 1 ? 'var(--green)' : undefined }} onClick={() => onRate(1)}><ThumbsUp size={14} /></button>
              <button className="btn btn-ghost !px-2" title={t('没用')} style={{ color: rating?.vote === -1 ? 'var(--red)' : undefined }} onClick={() => onRate(-1)}><ThumbsDown size={14} /></button>
              <button className="btn btn-ghost" onClick={() => window.biodsh.openPath(dir)}><FolderOpen size={13} /> {t('打开文件夹')}</button>
              <button className="btn btn-danger" onClick={() => { void uninstall(skill.id); }}><Trash2 size={13} /> {t('卸载')}</button>
            </div>
          )}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-6">
          {tab === 'overview' && (
            <div className="flex flex-col gap-5 rise">
              <p className="t-body selectable" style={{ fontSize: 14, lineHeight: '21px' }}>{skillSummary(skill, lang)}</p>
              {community ? (
                <div className="grid grid-cols-2 gap-3">
                  <Info label={t('分类')} value={`${skill.domain_zh ? t(skill.domain_zh) : '—'} / ${skill.subcategory ?? '—'}`} />
                  <Info label={t('使用门槛')} value={skill.level || '—'} />
                  <Info label={t('来源仓库')} value={skill.origin?.repo ?? '—'} sub={skill.origin?.path} />
                  <Info label={t('许可证')} value={skill.origin?.license ?? '—'} />
                  <Info label={t('类型')} value={skill.has_scripts ? t('附带脚本，安装后由智能体调用') : t('说明书型，教智能体怎么做')} />
                  <Info label={t('BioDSH 评测')} value={t('未评测，运行前请自行判断')} />
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <Info label={t('综合评分')} value={typeof skill.score === 'number' ? `${skill.score} / 100` : t('未评测')} sub={typeof skill.score === 'number' ? (skill.score_source ?? t('五维加权：正确性/鲁棒性/可复现/离线/效率')) : t('尚无公认 benchmark 分数')} />
                  {skill.benchmarks && skill.benchmarks.length > 0 && <Info label={t('计划接入 benchmark')} value={skill.benchmarks.join(' · ')} />}
                  <Info label={t('运行方式')} value={t('本机离线运行，数据不出电脑')} />
                  <Info label={t('可复现性')} value={skill.evidence?.reproducible ? t('同输入重跑结果逐字节一致') : t('未验证')} />
                  <Info label={t('评测')} value={skill.evidence?.tests ? t('独立评分器 {tests} 通过', { tests: skill.evidence.tests }) : t('暂无')} />
                  <Info label={t('验证数据集')} value={skill.evidence?.dataset ?? '—'} />
                  <Info label={t('需要')} value={t('Python 分析环境（scanpy）')} />
                  <Info label={t('标签')} value={skill.tags.join(' · ') || '—'} />
                </div>
              )}
              {community && skill.origin?.url && <button className="btn btn-ghost self-start" onClick={() => window.biodsh.openExternal(skill.origin!.url)}><ExternalLink size={13} /> {t('查看来源仓库')}</button>}
              {community && skill.name_en && lang !== 'en' && <div className="t-caption">{t('原名：{name}', { name: skill.name_en })}</div>}
              <div>
                <div className="t-headline mb-2">{t('怎么用')}</div>
                <ol className="t-body list-decimal pl-5 flex flex-col gap-1" style={{ color: 'var(--text-2)' }}>
                  <li>{t('点「获取」安装，再确认「分析环境」已就绪。')}</li>
                  <li>{t('回到「对话」，把数据文件放进工作区文件夹。')}</li>
                  <li>{t('用白话告诉智能体你要做什么。智能体会自己选用这个技能并运行。')}</li>
                </ol>
              </div>
            </div>
          )}
          {tab === 'io' && (
            <div className="flex flex-col gap-5 rise">
              {skill.inputs.length === 0 && skill.outputs.length === 0 ? (
                <div className="t-body" style={{ color: 'var(--text-2)' }}>{t('这个技能没有声明固定的输入输出，请看「原文说明书」。')}</div>
              ) : (
                <>
                  <div>
                    <div className="t-headline mb-2">{t('输入')}</div>
                    {skill.inputs.map((i) => <div key={i.name} className="flex items-center gap-2 t-body"><span className="badge">{i.format}</span><span>{i.name}</span>{i.required && <span className="t-caption">{t('必需')}</span>}</div>)}
                  </div>
                  <div>
                    <div className="t-headline mb-2">{t('输出（{n} 个文件）', { n: skill.outputs.length })}</div>
                    <div className="grid grid-cols-2 gap-1">{skill.outputs.map((o) => <div key={o} className="t-mono px-2 py-1 rounded-md" style={{ background: 'var(--surface-2)' }}>{o}</div>)}</div>
                  </div>
                </>
              )}
            </div>
          )}
          {tab === 'doc' && <div className="rise"><Markdown text={doc || t('（无说明）')} /></div>}
        </div>
      </div>
    </>
  );
}

function Info({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl px-3 py-2.5 min-w-0" style={{ background: 'var(--surface-2)' }}>
      <div className="t-caption">{label}</div>
      <div className="t-body mt-0.5 truncate" title={value}>{value}</div>
      {sub && <div className="t-caption truncate" title={sub}>{sub}</div>}
    </div>
  );
}
