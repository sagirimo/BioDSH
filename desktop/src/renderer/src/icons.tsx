// 统一图标：界面里不用 emoji，改用一套 lucide 线性图标（与其余 UI 同风格）。
import {
  Microscope, Dna, Table, LayoutGrid, Image as ImageIcon, FileText, Database, Package,
  BarChart3, Map, Stethoscope, Wrench, Pill, FlaskConical, Boxes, Shield, Bug,
  SlidersHorizontal, GitBranch, Activity, MousePointer2, BookText, Network,
  Layers, ScanLine, PenLine, Workflow, Beaker, ScatterChart, FileJson, type LucideIcon,
} from 'lucide-react';

const FILE_ICON: Record<string, LucideIcon> = {
  singlecell: Microscope, matrix: LayoutGrid, table: Table, figure: ImageIcon,
  seq: Dna, meta: FileJson, report: FileText, other: Package,
};
const PACK_ICON: Record<string, LucideIcon> = {
  '单细胞进阶': Microscope, 'Bulk RNA-seq': Dna, '空间转录组': Map,
  '统计与临床': Activity, '数据库访问': Database, '作图增强': BarChart3,
  '电脑控制': MousePointer2, '文献与格式桥接': BookText,
};
const DOMAIN_ICON: Record<string, LucideIcon> = {
  '单细胞与空间': Microscope, '转录组与表达': Dna, '基因组与变异': GitBranch,
  '表观与调控': SlidersHorizontal, '蛋白与结构': Boxes, '药物与化学': Pill,
  '临床与医学': Stethoscope, '微生物与免疫': Shield, '代谢与其他组学': FlaskConical,
  '数据与工具': Wrench,
};
const CATEGORY_ICON: Record<string, LucideIcon> = {
  genomics: Dna, database: Database, general: Package, clinical: Stethoscope,
  proteomics: Boxes, 'single-cell': Microscope, statistics: BarChart3,
  transcriptomics: Dna, workflow: Workflow, visualization: ScatterChart,
  drug: Pill, epigenomics: SlidersHorizontal, imaging: ScanLine, writing: PenLine,
  pathway: Network, immunology: Shield, spatial: Map, metagenomics: Bug,
  metabolomics: FlaskConical, tool: Wrench, analysis: Activity, qc: Activity,
  audit: Shield, literature: BookText,
};

export function FileTypeIcon({ type, size = 18 }: { type: string; size?: number }) {
  const I = FILE_ICON[type] ?? Package; return <I size={size} strokeWidth={1.75} />;
}
export function PackIcon({ name, size = 26 }: { name: string; size?: number }) {
  const I = PACK_ICON[name] ?? Package; return <I size={size} strokeWidth={1.6} />;
}
export function DomainIcon({ domain, size = 16 }: { domain: string; size?: number }) {
  const I = DOMAIN_ICON[domain] ?? Layers; return <I size={size} strokeWidth={1.75} />;
}
export function SkillIcon({ category, domain, size = 20 }: { category?: string; domain?: string; size?: number }) {
  const I = (category ? CATEGORY_ICON[category] : undefined) ?? (domain ? DOMAIN_ICON[domain] : undefined) ?? Beaker;
  return <I size={size} strokeWidth={1.7} />;
}
