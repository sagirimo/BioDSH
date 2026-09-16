// 数据库:按域分类分层浏览(不再平铺)+ 智能搜索(即时词法 + 回车语义向量,用包里的 e5 模型)。
// 每个库接真实技能;点示例问题或「让智能体抓取」→ 发给当前对话,智能体按对应技能的流程成体系地做。
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Search, Sparkles, ExternalLink, Loader2, Database as DbIcon } from 'lucide-react';
import { useT } from '../i18n';
import { useApp } from '../store';

interface Db { id: string; name: string; name_en?: string; url?: string; tags?: string[]; desc: string; skills?: string[]; examples?: string[]; _cat?: string; _catName?: string }
interface Cat { id: string; name: string; icon?: string; desc?: string; databases: Db[] }
interface Vectors { dim: number; ids: string[]; vecs: number[][] }

function cosine(a: number[], b: number[]) { let d = 0, na = 0, nb = 0; for (let i = 0; i < a.length; i++) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; } return d / (Math.sqrt(na) * Math.sqrt(nb) || 1); }

export default function DatabaseView() {
  const { t } = useT();
  const { dsh, currentSession, setTab } = useApp();
  const [cats, setCats] = useState<Cat[]>([]);
  const [vectors, setVectors] = useState<Vectors | null>(null);
  const [q, setQ] = useState('');
  const [ranked, setRanked] = useState<string[] | null>(null); // 语义搜索后的库 id 顺序(null=未搜索)
  const [searching, setSearching] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const allDbs = useRef<Db[]>([]);

  useEffect(() => { void (async () => {
    try {
      const r = await window.biodsh.dbCatalog() as { catalog: { categories: Cat[] }; vectors: Vectors };
      const cs = r.catalog.categories || [];
      cs.forEach((c) => c.databases.forEach((d) => { d._cat = c.id; d._catName = c.name; }));
      setCats(cs); setVectors(r.vectors && r.vectors.ids ? r.vectors : null);
      allDbs.current = cs.flatMap((c) => c.databases);
    } catch (e) { setNotice(`${t('数据库目录加载失败')}: ${String(e).slice(0, 80)}`); }
  })(); }, []);

  // 即时词法过滤(边打边筛)
  const lexHits = useMemo(() => {
    const s = q.trim().toLowerCase(); if (!s) return null;
    return allDbs.current.filter((d) => [d.name, d.name_en, d.desc, (d.tags || []).join(' '), (d.examples || []).join(' '), d._catName].join(' ').toLowerCase().includes(s)).map((d) => d.id);
  }, [q, cats]);

  // 回车 → 语义向量搜索(包里的 e5 模型),失败自动回退词法
  const semanticSearch = async () => {
    const s = q.trim(); if (!s || !vectors) return;
    setSearching(true);
    try {
      const qv = await window.biodsh.embedQuery(s) as number[];
      if (Array.isArray(qv) && qv.length === vectors.dim) {
        const scored = vectors.ids.map((id, i) => [id, cosine(qv, vectors.vecs[i])] as [string, number]);
        scored.sort((a, b) => b[1] - a[1]);
        // e5 分数聚在 0.85~0.93,不能用绝对阈值;取最相关的一簇:离最高分 0.05 以内,至少 3 个、最多 12 个。
        const top = scored[0]?.[1] ?? 0;
        setRanked(scored.filter(([, sc], i) => i < 3 || sc >= top - 0.05).slice(0, 12).map(([id]) => id));
      }
    } catch { setRanked(null); /* 回退到词法 lexHits */ }
    finally { setSearching(false); }
  };

  const byId = (id: string) => allDbs.current.find((d) => d.id === id);
  const go = async (d: Db, text: string) => {
    if (dsh.state !== 'running' || !currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体抓取')); setTimeout(() => setNotice(null), 4000); return; }
    try { await window.biodsh.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text }] }); setTab('chat'); }
    catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
  };
  const defaultPrompt = (d: Db) => t('请用「{db}」数据库帮我{q}。请优先使用与该数据库对应的技能、按其流程一步步完成,把结果整理到当前项目的工作区新子文件夹,并记录数据来源与查询条件。', { db: d.name, q: q.trim() || t('检索并整理我需要的数据（先问我具体要什么）') });

  const q2 = q.trim();
  const searchMode = q2.length > 0;
  const resultIds = ranked ?? lexHits;
  const DbCard = (d: Db) => (
    <div key={d.id} className="db-card">
      <div className="db-card-head">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><span className="t-body" style={{ fontWeight: 650 }}>{d.name}</span>{d.name_en && d.name_en !== d.name && <span className="t-caption" style={{ color: 'var(--text-3)' }}>{d.name_en}</span>}</div>
          <p className="t-caption" style={{ color: 'var(--text-2)', margin: '3px 0 0' }}>{d.desc}</p>
        </div>
        <button className="btn btn-tint shrink-0" onClick={() => go(d, defaultPrompt(d))}><Sparkles size={13} /> {t('让智能体抓取')}</button>
      </div>
      <div className="db-tags">
        {(d.tags || []).map((tg) => <span key={tg} className="db-tag">{tg}</span>)}
        {d.url && <a className="db-tag db-tag-link" href={d.url} target="_blank" rel="noreferrer">{t('官网')} <ExternalLink size={9} /></a>}
      </div>
      {(d.examples || []).length > 0 && <div className="db-examples">
        {(d.examples || []).map((ex, i) => <button key={i} className="db-example" title={t('点一下就让智能体去做')} onClick={() => go(d, t('用「{db}」数据库:{ex}。请用对应技能按流程完成,结果存到工作区新子文件夹并记录来源。', { db: d.name, ex }))}>{ex}</button>)}
      </div>}
    </div>
  );

  return (
    <div className="h-full flex flex-col">
      <div className="view-head">
        <DbIcon size={16} style={{ color: 'var(--accent)' }} /><span className="t-title2">{t('数据库')}</span>
        <span className="t-caption" style={{ color: 'var(--text-3)', marginLeft: 6 }}>{t('公共生信数据库,按需让智能体去查、下载、整理——不用记网址和 API')}</span>
      </div>
      <div className="db-search">
        <Search size={14} style={{ color: 'var(--text-3)' }} />
        <input className="db-search-input" value={q} placeholder={t('搜数据库(如:单细胞、卒中队列、蛋白结构、药物靶点…)——回车用语义搜索')}
          onChange={(e) => { setQ(e.target.value); setRanked(null); }}
          onKeyDown={(e) => { if (e.key === 'Enter') void semanticSearch(); }} />
        {searching ? <Loader2 size={14} className="spin" style={{ color: 'var(--accent)' }} /> : q2 && <button className="db-clear" onClick={() => { setQ(''); setRanked(null); }}>×</button>}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {notice && <div className="db-notice">{notice}</div>}

        {searchMode ? (
          <div className="pt-2">
            <div className="t-caption pb-2" style={{ color: 'var(--text-3)' }}>{ranked ? t('语义匹配结果') : t('匹配结果')}{resultIds ? t('（{n} 个）', { n: resultIds.length }) : ''}{!ranked && vectors && <span> · <button className="db-inline-link" onClick={() => void semanticSearch()}>{t('用语义搜索')}</button></span>}</div>
            {(resultIds || []).map((id) => { const d = byId(id); return d ? DbCard(d) : null; })}
            {resultIds && resultIds.length === 0 && <div className="t-caption py-6 text-center" style={{ color: 'var(--text-3)' }}>{t('没找到匹配的数据库,换个说法试试;或直接让智能体去查')}</div>}
          </div>
        ) : (
          <div className="pt-1">
            {cats.map((c) => { const open = !collapsed[c.id]; return (
              <div key={c.id} className="db-cat">
                <button className="db-cat-head" onClick={() => setCollapsed((s) => ({ ...s, [c.id]: open }))}>
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span className="t-body" style={{ fontWeight: 650 }}>{c.name}</span>
                  <span className="t-caption" style={{ color: 'var(--text-3)' }}>{c.databases.length}</span>
                  {c.desc && <span className="t-caption db-cat-desc">{c.desc}</span>}
                </button>
                {open && <div className="db-cat-body">{c.databases.map(DbCard)}</div>}
              </div>
            ); })}
            <p className="t-caption pt-3 pb-2" style={{ color: 'var(--text-3)' }}>{t('技能商店的「数据库/检索」分类里还有 200+ 个针对具体数据库的专业技能,智能体会自动挑合适的用。想要的数据库也可以反馈给我们,后续版本收录。')}</p>
          </div>
        )}
      </div>
    </div>
  );
}
