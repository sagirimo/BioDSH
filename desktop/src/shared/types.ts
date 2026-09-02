// 主进程 ↔ 渲染进程共享的类型。所有 IPC 都只传这些纯数据。

export type SkillCategory = 'qc' | 'analysis' | 'clinical' | 'audit' | 'other';

export interface SkillInput { name: string; format: string; required: boolean }

export interface CatalogSkill {
  id: string;
  name: string;
  summary: string;
  description: string;
  domain: string;
  category: SkillCategory | string;
  icon: string;
  tags: string[];
  inputs: SkillInput[];
  outputs: string[];
  offline: boolean;
  mutates_input: boolean;
  version: string;
  evidence: { tests?: string; offline?: boolean; reproducible?: boolean; dataset?: string } | null;
  score?: number | null;
  scoreBreakdown?: { correctness?: number; robustness?: number; reproducibility?: number; offline?: number; efficiency?: number } | null;
  score_source?: string;
  benchmarks?: string[] | null;
  featured: boolean;
  requires: { python: boolean; env: string };
  tier: 'official' | 'community';
  bundle: 'skills' | 'community-skills';
  origin?: { repo: string; url: string; path: string; license: string };
  has_scripts?: boolean;
  domain_zh?: string;
  subcategory?: string;
  level?: string;
  name_en?: string;
}

export type InstallState = 'not_installed' | 'installing' | 'installed' | 'update_available' | 'error';

export interface SkillStatus { id: string; state: InstallState; installedVersion?: string; error?: string }

export type EnvStep = 'idle' | 'python' | 'venv' | 'packages' | 'verify' | 'ready' | 'error';

export interface EnvStatus {
  ready: boolean;
  step: EnvStep;
  message: string;
  progress: number; // 0..1
  pythonPath?: string;
  pythonVersion?: string;
  packages?: Record<string, string>;
  log: string[];
}

export type DshState = 'stopped' | 'starting' | 'running' | 'error';

export interface DshStatus { state: DshState; url?: string; error?: string; log: string[] }

export interface AppSettings {
  useChinaMirror: boolean;
  workspace: string;
  onboarded: boolean;
  theme: 'system' | 'light' | 'dark';
  language: 'system' | 'zh' | 'en';
  /** 在线模式：DeepSeek 云端 API + 余额/更新等联网功能；离线模式：内网/本地模型接口，不发起任何外网请求 */
  mode: 'online' | 'offline';
  offlineBaseUrl: string;
  offlineModel: string;
  offlineApiKey: string;
  /** 离线模式可选：连接已部署在 Linux 服务器上的 dsh（不在本机启动） */
  remoteDshUrl: string;
  /** 图像生成：OpenAI 兼容 images 接口（智谱 CogView / OpenAI / SiliconFlow / 通义万相） */
  imageBaseUrl: string;
  imageApiKey: string;
  imageModel: string;
  /** 外接 MCP 服务 */
  mcpServers: McpServer[];
  demosSeeded: boolean;
}

export interface McpServer {
  name: string;
  transport: 'stdio' | 'streamable-http';
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  enabled?: boolean;
}

export interface RefPack { id: string; name: string; desc: string; group: string; sizeMb: number; installed: boolean; path: string }
export interface DemoInfo { id: string; title: string; path: string; registered: boolean }

export interface AppPaths { root: string; dshHome: string; bioenv: string; workspace: string; skills: string; logs: string }

export interface CredentialStatus { hasKey: boolean; masked?: string }

export interface Rect { x: number; y: number; width: number; height: number }

export type IpcEvent =
  | { type: 'env'; status: EnvStatus }
  | { type: 'dsh'; status: DshStatus }
  | { type: 'skills'; statuses: SkillStatus[] }
  | { type: 'skill-progress'; id: string; message: string }
  | { type: 'refdata'; id: string; received: number; total: number; done?: boolean };
