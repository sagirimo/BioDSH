// 数据库：常用公共生信数据库目录——一句白话说明 + 一键让智能体去抓取/查询（不用记网址和 API）。
import { useEffect, useState } from 'react';
import type { RefPack } from '@shared/types';
import { Globe, Sparkles, ExternalLink, Search, Download, Trash2, HardDrive, Check } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';

interface Db { id: string; name: string; desc: string; url: string; tags: string[]; prompt: string; group: string }
const DBS: Db[] = [
  { id: 'geo', name: 'GEO', group: '表达与测序数据', desc: 'NCBI 基因表达数据库：公开的芯片和测序数据集，用 GSE 编号检索下载。', url: 'https://www.ncbi.nlm.nih.gov/geo/', tags: ['RNA-seq', '单细胞'], prompt: '请帮我从 GEO 检索并下载数据集 {q}（或按我的描述找合适的数据集），下载到工作区新子文件夹，并整理成可分析的格式后告诉我它包含什么样本。' },
  { id: 'sra', name: 'SRA', group: '表达与测序数据', desc: '原始测序读段仓库（fastq），GEO 数据的原始文件在这里。', url: 'https://www.ncbi.nlm.nih.gov/sra', tags: ['fastq'], prompt: '请帮我从 SRA 获取 {q} 的原始测序数据（fastq），给出样本列表，先只下载一个小样本试跑。' },
  { id: 'tcga', name: 'TCGA / GDC', group: '临床与肿瘤', desc: '美国癌症基因组图谱：33 种癌症的表达、突变、临床随访数据。', url: 'https://portal.gdc.cancer.gov/', tags: ['肿瘤', '临床'], prompt: '请帮我从 TCGA (GDC) 获取 {q} 癌种的表达矩阵和临床信息，保存到工作区新子文件夹，并概述样本数与主要临床字段。' },
  { id: 'gtex', name: 'GTEx', group: '临床与肿瘤', desc: '正常人体各组织的基因表达图谱，常用于对照。', url: 'https://gtexportal.org/', tags: ['组织表达'], prompt: '请从 GTEx 获取基因 {q} 在各组织的表达情况并作图。' },
  { id: 'clinvar', name: 'ClinVar', group: '临床与肿瘤', desc: '基因变异与疾病关系的权威注释库。', url: 'https://www.ncbi.nlm.nih.gov/clinvar/', tags: ['变异', '致病性'], prompt: '请查询 ClinVar 中 {q}（基因或变异）的致病性注释并用通俗语言解释。' },
  { id: 'cellxgene', name: 'CELLxGENE', group: '单细胞图谱', desc: '整理好的单细胞图谱集合，可直接下载 h5ad。', url: 'https://cellxgene.cziscience.com/', tags: ['单细胞', 'h5ad'], prompt: '请在 CELLxGENE 找 {q} 相关的单细胞数据集，下载 h5ad 到工作区并做一次质控概览。' },
  { id: 'hca', name: 'Human Cell Atlas', group: '单细胞图谱', desc: '人类细胞图谱计划的数据门户。', url: 'https://data.humancellatlas.org/', tags: ['单细胞'], prompt: '请帮我在 Human Cell Atlas 找 {q} 组织的单细胞数据并说明如何下载。' },
  { id: 'uniprot', name: 'UniProt', group: '基因与蛋白', desc: '蛋白质序列与功能注释数据库。', url: 'https://www.uniprot.org/', tags: ['蛋白'], prompt: '请查询 UniProt 中 {q} 的功能、结构域和亚细胞定位，用通俗语言总结。' },
  { id: 'ensembl', name: 'Ensembl', group: '基因与蛋白', desc: '基因组注释：基因坐标、转录本、同源基因、ID 转换。', url: 'https://www.ensembl.org/', tags: ['注释', 'ID 转换'], prompt: '请用 Ensembl 把工作区里表格中的基因 ID {q} 转换成基因名并补充注释。' },
  { id: 'ncbi-gene', name: 'NCBI Gene', group: '基因与蛋白', desc: '基因基本信息与文献摘要。', url: 'https://www.ncbi.nlm.nih.gov/gene/', tags: ['基因'], prompt: '请查询 NCBI Gene 中 {q} 的功能概述、别名和相关疾病。' },
  { id: 'pdb', name: 'RCSB PDB', group: '基因与蛋白', desc: '蛋白质三维结构库。', url: 'https://www.rcsb.org/', tags: ['结构'], prompt: '请从 PDB 找 {q} 的结构条目，下载最合适的一个并简述其结构特点。' },
  { id: 'kegg', name: 'KEGG', group: '通路与功能', desc: '代谢与信号通路数据库。', url: 'https://www.kegg.jp/', tags: ['通路'], prompt: '请对工作区里的基因列表 {q} 做 KEGG 通路富集分析并作图解释。' },
  { id: 'go', name: 'Gene Ontology', group: '通路与功能', desc: '基因功能分类体系（生物过程 / 分子功能 / 细胞组分）。', url: 'http://geneontology.org/', tags: ['富集'], prompt: '请对基因列表 {q} 做 GO 富集分析，输出表格和气泡图，并用通俗语言解释前 10 条。' },
  { id: 'string', name: 'STRING', group: '通路与功能', desc: '蛋白互作网络。', url: 'https://string-db.org/', tags: ['互作网络'], prompt: '请用 STRING 构建基因列表 {q} 的互作网络，找出核心节点并作图。' },
  { id: 'msigdb', name: 'MSigDB', group: '通路与功能', desc: 'GSEA 用的基因集合集。', url: 'https://www.gsea-msigdb.org/', tags: ['GSEA'], prompt: '请用 MSigDB 的 Hallmark 基因集对工作区里的差异表达结果 {q} 做 GSEA。' },
  { id: 'pubmed', name: 'PubMed', group: '文献', desc: '生物医学文献库。', url: 'https://pubmed.ncbi.nlm.nih.gov/', tags: ['文献'], prompt: '请在 PubMed 检索「{q}」近 5 年的高引用文献，整理成表格（标题、年份、期刊、一句话结论）并总结研究趋势。' },
  { id: 'europepmc', name: 'Europe PMC', group: '文献', desc: '含全文的开放文献库，可抓取全文。', url: 'https://europepmc.org/', tags: ['全文'], prompt: '请通过 Europe PMC 找「{q}」的开放获取全文并总结方法与结论。' },
  { id: 'chembl', name: 'ChEMBL', group: '药物与化合物', desc: '生物活性化合物与靶点数据库。', url: 'https://www.ebi.ac.uk/chembl/', tags: ['药物'], prompt: '请在 ChEMBL 查询靶点 {q} 的已知活性化合物并整理成表。' },
  { id: 'drugbank', name: 'DrugBank', group: '药物与化合物', desc: '药物与靶点信息。', url: 'https://go.drugbank.com/', tags: ['药物'], prompt: '请查询与基因 {q} 相关的已上市药物及其作用机制。' },
];

export default function DatabaseView() {
  const { t } = useT();
  const { dsh, currentSession, setTab } = useApp();
  const [q, setQ] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const groups = [...new Set(DBS.map((d) => d.group))];
  const go = async (d: Db) => {
    if (dsh.state !== 'running' || !currentSession) { setNotice(t('先在左边选一个对话（或点「新对话」），再让智能体分析')); setTimeout(() => setNotice(null), 4000); return; }
    const text = d.prompt.replaceAll('{q}', q.trim() || t('（请先问我要检索什么）'));
    try { await window.biodsh.dshRpc('session.prompt', { sessionId: currentSession, mode: 'queue', content: [{ type: 'text', text: t(text) }] }); setTab('chat'); }
    catch (e) { setNotice(`${t('发送失败')}: ${String(e).slice(0, 80)}`); setTimeout(() => setNotice(null), 4000); }
  };
  return (
    <div className="h-full flex flex-col">
      <header className="drag h-[52px] flex items-center justify-between pl-5 pr-3 hairline-b" style={{ background: 'var(--bg)' }}>
        <span className="t-title2">{t('数据库')}</span>
        <div className="relative no-drag">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-3)' }} />
          <input className="field !h-[30px] !pl-8 w-[300px] !rounded-full" placeholder={t('要找什么？基因名 / 疾病 / GSE 编号 / 关键词')} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[1000px] mx-auto px-8 py-6 flex flex-col gap-6">
          {notice && <div className="px-3 py-2 rounded-lg t-body rise" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>{notice}</div>}
          <p className="t-body" style={{ color: 'var(--text-2)' }}>{t('在上面输入你关心的东西（比如一个基因、一种癌症、一个 GSE 编号），再点某个数据库的「让智能体抓取」，它会自己去查、下载、整理到当前项目的工作区。')}</p>
          {groups.map((g) => (
            <section key={g}>
              <div className="t-headline mb-2">{t(g)}</div>
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
                {DBS.filter((d) => d.group === g).map((d) => (
                  <div key={d.id} className="card p-4 flex flex-col gap-2 rise">
                    <div className="flex items-center gap-2"><Globe size={15} style={{ color: 'var(--accent)' }} /><span className="t-headline flex-1">{d.name}</span><button className="p-1 rounded-md hover:bg-[var(--fill)]" title={t('打开官网')} onClick={() => window.biodsh.openExternal(d.url)}><ExternalLink size={13} style={{ color: 'var(--text-3)' }} /></button></div>
                    <div className="t-body" style={{ color: 'var(--text-2)', minHeight: 36 }}>{t(d.desc)}</div>
                    <div className="flex flex-wrap gap-1.5">{d.tags.map((x) => <span key={x} className="badge">{t(x)}</span>)}</div>
                    <button className="btn btn-tint" onClick={() => go(d)}><Sparkles size={13} /> {t('让智能体抓取')}</button>
                  </div>
                ))}
              </div>
            </section>
          ))}
          <RefdataSection />
          <p className="t-caption pb-2" style={{ color: 'var(--text-3)' }}>{t('技能商店的「数据库/检索」分类里还有 200 多个针对具体数据库的技能，安装后智能体会用得更熟练。')}</p>
        </div>
      </div>
    </div>
  );
}

/** 本地参考包：常用基因集/注释文件下载到 ~/BioDSH/refdata，离线也能做富集和 ID 转换 */
function RefdataSection() {
  const { t } = useT();
  const [packs, setPacks] = useState<RefPack[]>([]);
  const [prog, setProg] = useState<Record<string, { received: number; total: number }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    void window.biodsh.refdataList().then(setPacks);
    return window.biodsh.onEvent((e) => { if (e.type === 'refdata') setProg((p) => ({ ...p, [e.id]: { received: e.received, total: e.total } })); });
  }, []);
  const install = async (id: string) => {
    setBusy(id); setErr(null);
    try { await window.biodsh.refdataInstall(id); setPacks(await window.biodsh.refdataList()); }
    catch (e) { setErr(`${t('下载失败')}: ${String(e).slice(0, 100)}`); }
    setBusy(null); setProg((p) => { const q = { ...p }; delete q[id]; return q; });
  };
  const groups = [...new Set(packs.map((p) => p.group))];
  const fmt = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);
  return (
    <section>
      <div className="flex items-center gap-2 mb-1"><HardDrive size={15} style={{ color: 'var(--accent)' }} /><span className="t-headline">{t('本地参考包')}</span></div>
      <p className="t-caption mb-3" style={{ color: 'var(--text-3)' }}>{t('把常用的基因集和注释文件下载到本机（~/BioDSH/refdata）。装了之后富集分析、ID 转换、互作网络不用联网，纯离线模式也能做；智能体会自动优先用本地文件。')}</p>
      {err && <div className="px-3 py-2 mb-2 rounded-lg t-body" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>{err}</div>}
      {groups.map((g) => (
        <div key={g} className="mb-3">
          <div className="t-caption mb-1.5" style={{ color: 'var(--text-2)' }}>{t(g)}</div>
          <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
            {packs.filter((p) => p.group === g).map((p) => {
              const pr = prog[p.id];
              return (
                <div key={p.id} className="card p-3 flex flex-col gap-1.5">
                  <div className="flex items-center gap-2"><span className="t-headline flex-1">{t(p.name)}</span><span className="badge">{p.sizeMb >= 1 ? `${p.sizeMb.toFixed(0)} MB` : `${(p.sizeMb * 1024).toFixed(0)} KB`}</span></div>
                  <div className="t-caption" style={{ color: 'var(--text-2)' }}>{t(p.desc)}</div>
                  {pr && <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--surface-2)' }}><div className="h-full" style={{ width: pr.total ? `${Math.min(100, (100 * pr.received) / pr.total)}%` : '30%', background: 'var(--accent)', transition: 'width .3s' }} /></div>}
                  <div className="flex items-center gap-2 mt-0.5">
                    {p.installed
                      ? <><span className="t-caption inline-flex items-center gap-1" style={{ color: 'var(--ok, #34c759)' }}><Check size={13} strokeWidth={2} /> {t('已下载')}</span><button className="btn btn-ghost ml-auto" onClick={() => window.biodsh.openPath(p.path.replace(/[\\/][^\\/]+$/, ''))}>{t('打开文件夹')}</button><button className="btn btn-ghost" onClick={async () => setPacks(await window.biodsh.refdataRemove(p.id))}><Trash2 size={12} /></button></>
                      : <button className="btn btn-tint" disabled={busy !== null} onClick={() => install(p.id)}><Download size={13} /> {busy === p.id ? (pr ? `${fmt(pr.received)}${pr.total ? ' / ' + fmt(pr.total) : ''}` : t('下载中…')) : t('下载')}</button>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </section>
  );
}
