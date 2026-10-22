import type { BioIconName } from './BioIcon';

// Match existing application keys. Display naming can change without migrating stored data.
export const NAV_ICONS = {
  chat: 'ui-project', skills: 'ui-skills', pipes: 'ui-workflows', db: 'ui-database',
  help: 'ui-help', settings: 'ui-settings',
} as const satisfies Record<string, BioIconName>;

export const DOMAIN_ICONS: Record<string, BioIconName> = {
  '单细胞与空间': 'domain-single-cell-spatial', '转录组与表达': 'domain-transcriptomics',
  '基因组与变异': 'domain-genomics-variants', '表观与调控': 'domain-epigenomics',
  '蛋白与结构': 'domain-protein-structure', '药物与化学': 'domain-drug-chemistry',
  '临床与医学': 'domain-clinical', '微生物与免疫': 'domain-microbiome-immunity',
  '代谢与其他组学': 'domain-metabolomics', '数据与工具': 'domain-data-tools',
};
export const FILE_ICONS: Record<string, BioIconName> = {
  singlecell:'file-anndata', matrix:'file-matrix', table:'file-table', figure:'file-image',
  seq:'file-sequence', meta:'file-metadata', report:'file-pdf', other:'file-generic',
  // Sidebar.workspaceFiles() returns a separate set of kind values.
  image:'file-image', code:'file-code', archive:'file-archive', text:'file-generic',
};
export const PACK_ICONS: Record<string, BioIconName> = {
  '单细胞进阶':'domain-single-cell-spatial', 'Bulk RNA-seq':'domain-transcriptomics',
  '空间转录组':'domain-single-cell-spatial', '统计与临床':'domain-clinical',
  '数据库访问':'ui-database', '作图增强':'file-image',
  '电脑控制':'domain-data-tools', '文献与格式桥接':'file-pdf',
};
export const CATEGORY_ICONS: Record<string, BioIconName> = {
  genomics:'domain-genomics-variants', database:'ui-database', general:'domain-data-tools',
  clinical:'domain-clinical', proteomics:'domain-protein-structure', 'single-cell':'domain-single-cell-spatial',
  statistics:'domain-data-tools', transcriptomics:'domain-transcriptomics', workflow:'ui-workflows',
  visualization:'file-image', drug:'domain-drug-chemistry', epigenomics:'domain-epigenomics',
  imaging:'file-image', writing:'file-pdf', pathway:'ui-workflows', immunology:'domain-microbiome-immunity',
  spatial:'domain-single-cell-spatial', metagenomics:'domain-microbiome-immunity',
  metabolomics:'domain-metabolomics', tool:'domain-data-tools', analysis:'domain-data-tools',
  qc:'ui-review', audit:'ui-review', literature:'ui-learn-workflow',
};
export function fileIconFor(kind: string, filename = ''): BioIconName {
  if (/\.h5ad$/i.test(filename)) return 'file-anndata';
  if (/\.(csv|tsv|xlsx?)$/i.test(filename)) return 'file-table';
  if (/\.(mtx|mtx\.gz)$/i.test(filename)) return 'file-matrix';
  if (/\.(fasta|fastq|fa|fq)(\.gz)?$/i.test(filename)) return 'file-sequence';
  if (/\.(pdf|docx?)$/i.test(filename)) return 'file-pdf';
  if (/\.(py|r|rmd|ipynb|sh|js|ts)$/i.test(filename)) return 'file-code';
  if (/\.(json|ya?ml|toml)$/i.test(filename)) return 'file-metadata';
  if (/\.(zip|gz|bz2|xz|tar|7z)$/i.test(filename)) return 'file-archive';
  return FILE_ICONS[kind] ?? 'file-generic';
}
