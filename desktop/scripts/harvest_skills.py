#!/usr/bin/env python3
"""把 competitors/ 下各家 agent 技能库里的生信 SKILL.md 收编为商店的「社区技能」。

流程：扫描 → 解析 frontmatter → 生信过滤 → 去重（原始仓优先于聚合仓；同名不同内容则并存）
     → 统一分类 → 复制到 desktop/resources/community-skills/<id>/ → 写 store/community-index.json
只复制轻量文件（单文件 ≤ MAX_FILE，整目录 ≤ MAX_DIR），保证安装包体积可控。
"""
from __future__ import annotations
import csv, hashlib, json, os, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # BioDSH/
COMP = ROOT / 'competitors'
OUT_SKILLS = ROOT / 'desktop' / 'resources' / 'community-skills'
OUT_INDEX = ROOT / 'desktop' / 'store' / 'community-index.json'
MAX_FILE = 300 * 1024
MAX_DIR = 3 * 1024 * 1024
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.ipynb_checkpoints'}
SKIP_EXT = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe', '.zip', '.tar', '.gz', '.h5ad', '.h5', '.bam', '.fastq', '.fq', '.rds', '.parquet', '.pt', '.pth', '.bin'}

# 来源仓：优先级越小越优先（原始仓 < 聚合仓）。include 为空表示整仓，否则只收这些前缀。exclude 为路径片段。
SOURCES = [
    dict(key='biodsh-omicverse', repo='OmicVerse', dir='OmicVerse', license='GPL-3.0', url='https://github.com/Starlitnightly/omicverse', prio=1, include=['.claude/skills']),
    dict(key='clawbio', repo='ClawBio', dir='ClawBio', license='MIT', url='https://github.com/ClawBio/ClawBio', prio=1, include=['skills']),
    dict(key='gptomics', repo='GPTomics-bioSkills', dir='GPTomics-bioSkills', license='MIT', url='https://github.com/GPTomics/bioSkills', prio=1, include=[], exclude=['clawhub-installer']),
    dict(key='memomics', repo='MemOmics-Agent', dir='MemOmics-Agent', license='MIT', url='https://github.com/MemOmics/MemOmics-Agent', prio=1, include=['hermes_home/skills/bioinformatics']),
    dict(key='sciagent', repo='SciAgent-Skills', dir='SciAgent-Skills', license='CC-BY-4.0', url='https://github.com/SciAgent/SciAgent-Skills', prio=1, include=[]),
    dict(key='bioharness', repo='BioHarness', dir='BioHarness', license='MIT', url='https://github.com/BioHarness/BioHarness', prio=1, include=['bio_harness/skills']),
    dict(key='hcls', repo='hcls-agent-skills', dir='hcls-agent-skills', license='Apache-2.0', url='https://github.com/aws-samples/hcls-agent-skills', prio=1, include=['skills']),
    dict(key='omics-skills', repo='omics-skills', dir='omics-skills', license='MIT', url='https://github.com/omics-skills/omics-skills', prio=1, include=['skills']),
    dict(key='pantheon', repo='pantheonos', dir='pantheonos', license='BSD-2-Clause', url='https://github.com/pantheonos/pantheonos', prio=1, include=[]),
    dict(key='bionexus', repo='BioNexus', dir='BioNexus', license='unknown', url='', prio=1, include=['skills']),
    dict(key='cab', repo='CAB-aiSkills', dir='CAB-aiSkills', license='CC-BY-4.0', url='', prio=1, include=[]),
    dict(key='caribou', repo='CARIBOU', dir='CARIBOU', license='MIT', url='', prio=1, include=['skills']),
    dict(key='biodsa', repo='BioDSA', dir='BioDSA', license='unknown', url='', prio=1, include=[]),
    dict(key='lobster', repo='OmicsOS-Lobster', dir='OmicsOS-Lobster', license='unknown', url='', prio=1, include=[]),
    dict(key='awesome', repo='awesome-bio-agent-skills', dir='awesome-bio-agent-skills', license='CC0-1.0', url='https://github.com/awesome-bio-agent-skills', prio=5, include=['skills']),
]

CATEGORIES = {  # 统一分类 → (中文名, 关键词)
    'single-cell': ('单细胞', r'single[- ]?cell|scrna|scanpy|seurat|10x|cell ?type|clustering|umap|leiden|annotation|scvi|cellranger|doublet|trajectory|pseudotime|velocity|cellphonedb|cell ?chat|scatac'),
    'spatial': ('空间组学', r'spatial|visium|xenium|merfish|squidpy|stagent|slide-?seq|imaging mass'),
    'transcriptomics': ('转录组', r'rna-?seq|deseq2|edger|limma|differential expression|deg\b|salmon|kallisto|star align|featurecounts|splicing|isoform|expression matrix|bulk'),
    'genomics': ('基因组', r'genom|variant|vcf|gwas|snp|bwa|gatk|bcftools|samtools|bed\b|interval|assembly|annotation|cnv|copy number|structural variant|liftover|fasta|fastq|alignment|bam\b|crispr|plink'),
    'epigenomics': ('表观组', r'atac|chip-?seq|methyl|bisulfite|histone|peak|macs|hi-?c|chromatin|cut&?tag|cut&?run|enhancer'),
    'proteomics': ('蛋白/结构', r'proteom|mass spec|maxquant|peptide|protein structure|alphafold|pdb|docking|molecular dynamics|binder|esm|rosetta|foldseek|ppi'),
    'metabolomics': ('代谢组', r'metabolom|lipidom|metabolite|ms/ms|xcms|hmdb'),
    'metagenomics': ('微生物/宏基因组', r'metagenom|microbiom|16s|qiime|kraken|taxonom|amplicon|virome'),
    'immunology': ('免疫', r'immun|tcr|bcr|hla|epitope|antibody|vdj|neoantigen|flow cytometry|cytof'),
    'clinical': ('临床/医学', r'clinical|patient|trial|survival|cox|kaplan|ehr|fhir|icd|oncolog|tumou?r|cancer|tcga|drug response|pharmac|biomarker|diagnos|epidemiolog'),
    'drug': ('药物/化学', r'drug|chem|smiles|rdkit|admet|docking|compound|ligand|qsar|molecul|pubchem|chembl'),
    'pathway': ('通路/富集', r'pathway|enrich|gsea|go term|kegg|reactome|gene set|ora\b|msigdb'),
    'database': ('数据库/检索', r'database|api|query|fetch|download|ncbi|ensembl|uniprot|geo\b|sra|pubmed|literature|search|retriev|entrez|biomart'),
    'visualization': ('可视化/作图', r'plot|visuali|figure|heatmap|volcano|ggplot|matplotlib|seaborn|plotly|igv|chart'),
    'statistics': ('统计/机器学习', r'statist|regression|bayes|machine learning|deep learning|model|classif|cluster|pca\b|dimension|xgboost|random forest|neural'),
    'workflow': ('流程/工程', r'workflow|pipeline|nextflow|snakemake|wdl|cwl|docker|conda|environment|install|slurm|hpc|nf-core|reproduc|provenance|qc\b|quality control|multiqc'),
    'imaging': ('影像', r'imag|microscop|segment|cellpose|histolog|pathology|radiolog|dicom|napari'),
    'writing': ('写作/报告', r'writing|manuscript|report|grant|citation|latex|review|summar|presentation'),
}
BIO_HINT = re.compile('|'.join(v[1] for k, v in CATEGORIES.items() if k not in ('writing', 'workflow', 'statistics', 'visualization', 'database')), re.I)
NONBIO = re.compile(r'google meet|calendar|slack|discord|recommendation letter|tailoring application|humaniz|deslop|yuanbao|dogfood|wechat|weixin|zoom|notion|jira|\bemail|feishu|lark|dingtalk|telegram|whatsapp|twitter|weibo|bilibili|douyin|obsidian|todo list|clawhub|skill-creator|skill creator|installer', re.I)

def parse_frontmatter(text: str) -> dict:
    m = re.match(r'^﻿?---\s*\r?\n(.*?)\r?\n---', text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        if not line or line.startswith((' ', '\t', '-', '#')):
            continue
        k, _, v = line.partition(':')
        v = v.strip().strip('"\'')
        if v.startswith(('>', '|')):
            v = ''
        fm[k.strip()] = v
    return fm

def first_paragraph(body: str) -> str:
    body = re.sub(r'^﻿?---.*?---', '', body, count=1, flags=re.S)
    for para in re.split(r'\n\s*\n', body):
        p = ' '.join(l.strip() for l in para.strip().split('\n'))
        p = re.sub(r'^#+\s*', '', p)
        if len(p) > 30 and not p.startswith(('```', '|', '<', '[')):
            return p[:400]
    return ''

def kebab(s: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return re.sub(r'-{2,}', '-', s)[:64] or 'skill'

def categorize(name: str, desc: str, hint: str) -> str:
    text = f'{name} {desc}'
    hint = (hint or '').lower()
    alias = {'single-cell': 'single-cell', 'genomics': 'genomics', 'proteomics': 'proteomics', 'transcriptomics': 'transcriptomics', 'epigenomics': 'epigenomics', 'metagenomics': 'metagenomics', 'clinical': 'clinical', 'database-query': 'database', 'visualization': 'visualization', 'workflow': 'workflow', 'pathway': 'pathway', 'protein-design': 'proteomics', 'multi-omics': 'statistics'}
    scores = {k: len(re.findall(v[1], text, re.I)) for k, v in CATEGORIES.items()}
    if hint in alias:
        scores[alias[hint]] += 3
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'

def dir_size_ok(d: Path) -> tuple[int, list[Path]]:
    files, total = [], 0
    for p in d.rglob('*'):
        if any(part in SKIP_DIRS for part in p.relative_to(d).parts):
            continue
        if p.is_file():
            if p.suffix.lower() in SKIP_EXT or p.stat().st_size > MAX_FILE:
                continue
            files.append(p); total += p.stat().st_size
    return total, files

def main():
    # awesome 聚合仓自带索引：folder_name → category，作为分类提示
    hint_by_folder = {}
    csvp = COMP / 'awesome-bio-agent-skills' / 'bioskill_index_v3.csv'
    if csvp.exists():
        for r in csv.DictReader(open(csvp, encoding='utf-8')):
            hint_by_folder[r['folder_name']] = r['category']

    candidates = []
    for src in SOURCES:
        base = COMP / src['dir']
        if not base.exists():
            print('missing', src['dir'], file=sys.stderr); continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            if 'SKILL.md' not in fns:
                continue
            skill_md = Path(dp) / 'SKILL.md'
            rel = skill_md.parent.relative_to(base).as_posix()
            if src.get('include') and not any(rel == i or rel.startswith(i + '/') for i in src['include']):
                continue
            if any(x in rel for x in src.get('exclude', [])):
                continue
            try:
                text = skill_md.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            text = re.sub(r'^\ufeff?\s*(<!--.*?-->\s*)+', '', text, count=1, flags=re.S)
            fm = parse_frontmatter(text)
            raw_name = fm.get('name') or skill_md.parent.name
            name = kebab(raw_name)
            desc = (fm.get('description') or first_paragraph(text)).strip()
            if not desc:
                desc = first_paragraph(text)
            probe = f'{name} {desc} {rel}'
            if NONBIO.search(probe):
                continue
            # 生信过滤：名字/描述/路径里要能看到生物学线索；聚合仓与 GPTomics/MemOmics 生信子目录默认放行
            if src['key'] not in ('awesome', 'gptomics', 'memomics', 'clawbio', 'omics-skills', 'biodsh-omicverse', 'hcls', 'cab', 'bioharness') and not BIO_HINT.search(probe):
                continue
            body_hash = hashlib.sha1(re.sub(r'\s+', ' ', re.sub(r'^﻿?---.*?---', '', text, count=1, flags=re.S)).strip().encode()).hexdigest()[:12]
            candidates.append(dict(
                name=name, raw_name=raw_name, description=desc[:500], src=src, rel=rel, dir=skill_md.parent,
                body_hash=body_hash, hint=hint_by_folder.get(skill_md.parent.name, ''),
                version=fm.get('version', ''), author=fm.get('author', ''), license=fm.get('license') or src['license'],
                tags=[t.strip() for t in re.split(r'[,\s]+', fm.get('tags', '').strip('[]')) if t.strip()][:8],
            ))
    print('candidates', len(candidates))

    # 去重：同 body_hash 只留优先级最高的一份；同名不同内容 → 后来的加来源后缀
    candidates.sort(key=lambda c: (c['src']['prio'], c['src']['key'], c['rel']))
    seen_hash, taken_ids, kept, name_prio = set(), set(), [], {}
    for c in candidates:
        if c['body_hash'] in seen_hash:
            continue
        seen_hash.add(c['body_hash'])
        base = c['name'][:48].rstrip('-')          # 先截断再加后缀，否则后缀被截掉会死循环
        if base in name_prio and name_prio[base] < c['src']['prio']:
            continue                                 # 聚合仓里的同名转载，丢弃
        name_prio.setdefault(base, c['src']['prio'])
        sid = base
        if sid in taken_ids:
            sid = f"{base}-{c['src']['key']}"
            n = 2
            while sid in taken_ids:
                sid = f"{base}-{c['src']['key']}-{n}"; n += 1
        taken_ids.add(sid); c['id'] = sid; kept.append(c)
    print('after dedupe', len(kept))

    # 复制 + 写索引
    if OUT_SKILLS.exists():
        shutil.rmtree(OUT_SKILLS)
    OUT_SKILLS.mkdir(parents=True)
    index, skipped_big, total_bytes = [], 0, 0
    for c in kept:
        total, files = dir_size_ok(c['dir'])
        if total > MAX_DIR:
            skipped_big += 1
            continue
        dst = OUT_SKILLS / c['id']
        for f in files:
            t = dst / f.relative_to(c['dir'])
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
        # 规范 SKILL.md：frontmatter 的 name 必须等于目录 id（dsh 要求 kebab-case、同层唯一），补齐缺失的 description
        md = dst / 'SKILL.md'
        text = md.read_text(encoding='utf-8', errors='ignore')
        text = re.sub(r'^\ufeff?\s*(<!--.*?-->\s*)+', '', text, count=1, flags=re.S)
        body = re.sub(r'^﻿?---.*?---\s*', '', text, count=1, flags=re.S)
        desc_line = c['description'].replace('\n', ' ').replace('"', "'")
        text = f'---\nname: {c["id"]}\ndescription: "{desc_line}"\n---\n\n{body}'
        md.write_text(text, encoding='utf-8')
        total_bytes += total
        has_scripts = any(f.suffix in ('.py', '.R', '.sh') for f in files)
        index.append(dict(
            id=c['id'], name=c['raw_name'] if c['raw_name'] != c['name'] else c['id'].replace('-', ' ').title(),
            description=c['description'], category=categorize(c['name'], c['description'], c['hint']),
            tags=c['tags'], version=c['version'] or '1.0.0', author=c['author'],
            origin=dict(repo=c['src']['repo'], url=c['src']['url'], path=c['rel'], license=c['license']),
            has_scripts=has_scripts, files=len(files), size=total,
        ))
    OUT_INDEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_INDEX.write_text(json.dumps(dict(meta=dict(count=len(index), sources=[s['repo'] for s in SOURCES]), skills=index), ensure_ascii=False, indent=1), encoding='utf-8')
    from collections import Counter
    print('written', len(index), 'skipped big', skipped_big, 'total MB', round(total_bytes / 1e6, 1))
    print('by category', Counter(i['category'] for i in index).most_common())
    print('by repo', Counter(i['origin']['repo'] for i in index).most_common())

if __name__ == '__main__':
    main()
