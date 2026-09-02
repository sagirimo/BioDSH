import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import UpdateCheck from '../components/UpdateCheck';
import { ExternalLink, FolderOpen, KeyRound } from 'lucide-react';
import { useApp } from '../store';
import type { McpServer } from '@shared/types';
import { useT } from '../i18n';

// OpenAI 兼容的模型提供商预设：选一个自动填「接口地址 + 模型名」，也可手填。
// dsh 引擎走 chat/completions 协议，这些都是兼容端点；Anthropic 原生协议暂不支持。
const PROVIDERS: { id: string; label: string; base: string; model: string }[] = [
  { id: 'deepseek', label: 'DeepSeek 官方', base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { id: 'openai', label: 'OpenAI (Codex / GPT)', base: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { id: 'moonshot', label: 'Moonshot Kimi', base: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-32k' },
  { id: 'qwen', label: '通义千问 DashScope', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { id: 'zhipu', label: '智谱 GLM', base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus' },
  { id: 'siliconflow', label: '硅基流动 SiliconFlow', base: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
];

export default function SettingsView() {
  const { settings, updateSettings, credential, saveKey, info, restartDsh } = useApp();
  const { t } = useT();
  const [key, setKey] = useState('');
  const offline = settings?.mode === 'offline';
  const [draft, setDraft] = useState<{ offlineBaseUrl?: string; offlineModel?: string; offlineApiKey?: string; remoteDshUrl?: string }>({});
  const saveOffline = async () => { await updateSettings(draft); setDraft({}); void restartDsh(); };
  const [saved, setSaved] = useState(false);
  const [upd, setUpd] = useState<{ dsh: { current: string; latest: string; outdated: boolean } } | null | 'checking' | 'error'>(null);
  const checkUpd = async () => { setUpd('checking'); try { setUpd(await window.biodsh.checkUpdates() as { dsh: { current: string; latest: string; outdated: boolean } }); } catch { setUpd('error'); } };
  useEffect(() => { setSaved(false); }, [key]);
  if (!settings) return null;
  const submit = async () => { await saveKey(key); setKey(''); setSaved(true); };
  return (
    <div className="h-full flex flex-col">
      <header className="drag h-[52px] flex items-center justify-between pl-5 hairline-b" style={{ background: 'var(--bg)' }}>
        <span className="t-title2">{t('设置')}</span>
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[720px] mx-auto px-8 py-8 flex flex-col gap-6">
          <Section title={t('运行模式')} desc={t('在线模式走 DeepSeek 云端接口；纯离线模式面向医院/内网：连本地或内网的模型接口，软件不发起任何外网请求（余额、更新检查等联网功能自动关闭）。')}>
            <div className="seg">
              {(['online', 'offline'] as const).map((k) => <button key={k} className={(settings.mode ?? 'online') === k ? 'active' : ''} onClick={async () => { await updateSettings({ mode: k }); void restartDsh(); }}>{t({ online: '在线模式', offline: '纯离线模式' }[k])}</button>)}
            </div>
            {offline && (
              <div className="flex flex-col gap-2 mt-3">
                <label className="t-caption">{t('提供商预设（选一个自动填地址和模型，也可手填）')}</label>
                <select className="field" value="" onChange={(e) => { const p = PROVIDERS.find((x) => x.id === e.target.value); if (p) setDraft((d) => ({ ...d, offlineBaseUrl: p.base, offlineModel: p.model })); }}>
                  <option value="">{t('选择提供商…')}</option>
                  {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
                <label className="t-caption">{t('模型接口地址（OpenAI/DeepSeek 兼容，例如 http://192.168.1.10:8000/v1）')}</label>
                <input className="field t-mono" placeholder="http://…" value={draft.offlineBaseUrl ?? settings.offlineBaseUrl ?? ''} onChange={(e) => setDraft((d) => ({ ...d, offlineBaseUrl: e.target.value }))} />
                <div className="flex gap-2">
                  <div className="flex-1 flex flex-col gap-1"><label className="t-caption">{t('模型名称')}</label><input className="field t-mono" placeholder="qwen3-32b / deepseek-r1 …" value={draft.offlineModel ?? settings.offlineModel ?? ''} onChange={(e) => setDraft((d) => ({ ...d, offlineModel: e.target.value }))} /></div>
                  <div className="flex-1 flex flex-col gap-1"><label className="t-caption">{t('接口密钥（内网服务不需要就留空）')}</label><input className="field t-mono" type="password" value={draft.offlineApiKey ?? settings.offlineApiKey ?? ''} onChange={(e) => setDraft((d) => ({ ...d, offlineApiKey: e.target.value }))} /></div>
                </div>
                <label className="t-caption mt-1">{t('远程 dsh 服务器（可选）：课题组已在 Linux 服务器部署 dsh 时填它的地址，本机就不再启动智能体')}</label>
                <input className="field t-mono" placeholder="http://192.168.1.10:3080" value={draft.remoteDshUrl ?? settings.remoteDshUrl ?? ''} onChange={(e) => setDraft((d) => ({ ...d, remoteDshUrl: e.target.value }))} />
                <div className="t-caption" style={{ color: 'var(--text-3)' }}>{t('服务器上启动命令示例：dsh web --host 0.0.0.0 --trusted-host 服务器IP:3080')}</div>
                <div><button className="btn btn-primary" disabled={Object.keys(draft).length === 0} onClick={saveOffline}>{t('保存并重启智能体')}</button></div>
                <div className="t-caption" style={{ color: 'var(--text-3)' }}>{t('以上均为 OpenAI 兼容接口；BioDSH 引擎(dsh)走 chat/completions 协议。Claude/Anthropic 原生协议暂不支持；非 DeepSeek 模型在 dsh 上的效果不保证。')}</div>
              </div>
            )}
          </Section>

          <Section title={t('模型 API Key')} desc={t('DeepSeek 的密钥。保存在本机 dsh-home/.credentials.yaml，只用于调用模型。')}>
            <div className="flex items-center gap-3">
              <div className="relative flex-1">
                <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-3)' }} />
                <input className="field !pl-9 t-mono" type="password" placeholder={credential.hasKey ? t('已设置 {masked}，输入新值可替换', { masked: credential.masked ?? '' }) : 'sk-…'} value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && key && submit()} />
              </div>
              <button className="btn btn-primary" disabled={!key.trim()} onClick={submit}>{saved ? t('已保存') : t('保存')}</button>
            </div>
            <div className="flex items-center gap-3 mt-3">
              <button className="btn btn-ghost" onClick={() => window.biodsh.openExternal('https://platform.deepseek.com/api_keys')}><ExternalLink size={13} /> {t('去 DeepSeek 开放平台申请')}</button>
              {credential.hasKey && <span className="t-caption">{t('已保存，智能体已自动重启使其生效')}</span>}
            </div>
          </Section>

          <Section title={t('工作区')} desc={t('智能体读写文件的文件夹。把要分析的数据放进去。')}>
            <div className="flex items-center gap-3">
              <div className="field flex items-center t-mono truncate flex-1" style={{ color: 'var(--text-2)' }}>{settings.workspace}</div>
              <button className="btn btn-fill" onClick={async () => { const p = await window.biodsh.pickFolder(); if (p) { await updateSettings({ workspace: p }); void restartDsh(); } }}>{t('更改…')}</button>
              <button className="btn btn-ghost" onClick={() => window.biodsh.openPath(settings.workspace)}><FolderOpen size={13} /></button>
            </div>
          </Section>

          <Section title={t('下载来源')} desc={t('在国内建议开启，Python 与软件包会从国内镜像下载，快很多。')}>
            <Toggle checked={settings.useChinaMirror} onChange={(v) => updateSettings({ useChinaMirror: v })} label={t('使用国内镜像')} />
          </Section>

          <Section title={t('外观')}>
            <div className="seg">
              {(['system', 'light', 'dark'] as const).map((k) => <button key={k} className={settings.theme === k ? 'active' : ''} onClick={() => updateSettings({ theme: k })}>{t({ system: '跟随系统', light: '浅色', dark: '深色' }[k])}</button>)}
            </div>
          </Section>

          <Section title={t('语言 / Language')} desc={t('界面与智能体界面一起切换；智能体回答会跟随你提问的语言。')}>
            <div className="seg">
              {(['system', 'zh', 'en'] as const).map((k) => <button key={k} className={(settings.language ?? 'system') === k ? 'active' : ''} onClick={() => updateSettings({ language: k })}>{{ system: t('跟随系统'), zh: '中文', en: 'English' }[k]}</button>)}
            </div>
          </Section>

          <MigrateSection />

          <ImageSection />
          <McpSection />
          <DemosSection />

          <Section title={t('关于')}>
            <div className="t-body flex flex-col gap-1" style={{ color: 'var(--text-2)' }}>
              <div>{t('BioDSH Desktop v{v} · DeepSeek Harness 内核 v{dsh}', { v: info?.version ?? '', dsh: (info as { dshVersion?: string } | null)?.dshVersion ?? '?' })}</div>
              <UpdateCheck currentVersion={info?.version} />
              <div className="flex items-center gap-2">
                <button className="btn btn-ghost" onClick={checkUpd}><RefreshCw size={13} /> {t('检查 dsh 内核版本')}</button>
                {upd === 'checking' && <span className="t-caption">{t('正在检查…')}</span>}
                {upd === 'error' && <span className="t-caption">{t('检查失败（网络？）')}</span>}
                {upd && typeof upd === 'object' && (upd.dsh.outdated
                  ? <span className="t-caption" style={{ color: 'var(--orange)' }}>{t('dsh 内核有新版 {latest}（当前 {current}），等 BioDSH 下个安装包一并更新', { latest: upd.dsh.latest, current: upd.dsh.current })}</span>
                  : <span className="t-caption" style={{ color: 'var(--green)' }}>{t('dsh 内核已是最新（{current}）', { current: upd.dsh.current })}</span>)}
              </div>
              <div className="t-caption">{t('你的设置、API Key、分析环境和已装技能都在数据目录里，升级安装包不会丢失。')}</div>
              <div className="t-mono">{t('数据目录：{path}', { path: info?.paths.root ?? '' })}</div>
              <div className="flex gap-2 mt-2">
                <button className="btn btn-ghost" onClick={() => info && window.biodsh.openPath(info.paths.root)}><FolderOpen size={13} /> {t('打开数据目录')}</button>
                <button className="btn btn-ghost" onClick={() => updateSettings({ onboarded: false })}>{t('重新看一遍引导')}</button>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <section className="card p-5 rise">
      <div className="t-headline">{title}</div>
      {desc && <div className="t-caption mt-0.5 mb-3">{desc}</div>}
      {!desc && <div className="mb-3" />}
      {children}
    </section>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center justify-between t-body">
      <span>{label}</span>
      <button role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="relative w-[38px] h-[22px] rounded-full transition-colors" style={{ background: checked ? 'var(--green)' : 'var(--fill-2)' }}>
        <span className="absolute top-[2px] w-[18px] h-[18px] rounded-full bg-white shadow transition-all" style={{ left: checked ? 18 : 2 }} />
      </button>
    </label>
  );
}

interface MigrateSource { id: string; name: string; path: string; skills: string[]; instructions?: string | null; mcpServers: string[] }
function MigrateSection() {
  const { t } = useT();
  const { refresh } = useApp();
  const [sources, setSources] = useState<MigrateSource[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const scan = async () => { try { setSources(await window.biodsh.migrateScan() as MigrateSource[]); } catch { setSources([]); } };
  useEffect(() => { void scan(); }, []);
  const doImport = async (src: MigrateSource) => {
    setBusy(src.id);
    try {
      const r = await window.biodsh.migrateImport(src.id) as { skills: number; instructions: number; skipped: string[] };
      setMsg(t('已从 {name} 导入 {n} 个技能{extra}', { name: src.name, n: r.skills, extra: r.instructions ? t('，并合并了全局说明到工作区 AGENTS.md') : '' }));
      await refresh();
    } catch (e) { setMsg(`${t('导入失败')}: ${String(e).slice(0, 100)}`); }
    finally { setBusy(null); }
  };
  return (
    <Section title={t('从其他工具一键迁移')} desc={t('自动查找你在 Claude Code、Codex、OpenCode、Cursor 里已有的技能（SKILL.md）和全局说明（AGENTS.md / CLAUDE.md），复制进 BioDSH，原文件不动。')}>
      {sources === null && <div className="t-caption">{t('正在扫描…')}</div>}
      {sources !== null && sources.length === 0 && <div className="t-body" style={{ color: 'var(--text-2)' }}>{t('这台电脑上没有找到其他工具的技能或说明文件。')}</div>}
      <div className="flex flex-col gap-2">
        {(sources ?? []).map((s) => (
          <div key={s.id} className="flex items-center gap-3 rounded-xl px-3 py-2.5" style={{ background: 'var(--surface-2)' }}>
            <div className="flex-1 min-w-0">
              <div className="t-headline">{s.name}</div>
              <div className="t-caption truncate">{t('{n} 个技能', { n: s.skills.length })}{s.instructions ? ` · ${t('全局说明')}` : ''}{s.mcpServers.length ? ` · ${t('{n} 个 MCP 服务（暂不导入）', { n: s.mcpServers.length })}` : ''}{s.path ? ` · ${s.path}` : ''}</div>
            </div>
            <button className="btn btn-primary" disabled={busy === s.id || (s.skills.length === 0 && !s.instructions)} onClick={() => doImport(s)}>{busy === s.id ? t('导入中…') : t('导入')}</button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 mt-3"><button className="btn btn-ghost" onClick={scan}><RefreshCw size={13} /> {t('重新扫描')}</button>{msg && <span className="t-caption">{msg}</span>}</div>
    </Section>
  );
}

const IMAGE_PRESETS: { name: string; base: string; model: string; hint: string }[] = [
  { name: '智谱 CogView', base: 'https://open.bigmodel.cn/api/paas/v4', model: 'cogview-4-250304', hint: 'bigmodel.cn 申请 key，国内直连' },
  { name: '通义万相', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'wan2.2-t2i-flash', hint: '阿里云百炼，国内直连' },
  { name: 'SiliconFlow', base: 'https://api.siliconflow.cn/v1', model: 'Kwai-Kolors/Kolors', hint: '硅基流动，国内直连' },
  { name: 'OpenAI', base: 'https://api.openai.com/v1', model: 'gpt-image-1', hint: '需要能访问 OpenAI' },
];

/** 图像生成：给「AI 科研插图生成」技能用的 OpenAI 兼容 images 接口 */
function ImageSection() {
  const { settings, updateSettings, restartDsh } = useApp();
  const { t } = useT();
  const [d, setD] = useState<{ imageBaseUrl?: string; imageModel?: string; imageApiKey?: string }>({});
  const [saved, setSaved] = useState(false);
  if (!settings) return null;
  const cur = { imageBaseUrl: d.imageBaseUrl ?? settings.imageBaseUrl ?? '', imageModel: d.imageModel ?? settings.imageModel ?? '', imageApiKey: d.imageApiKey ?? settings.imageApiKey ?? '' };
  const save = async () => { await updateSettings(cur); setD({}); setSaved(true); setTimeout(() => setSaved(false), 2500); void restartDsh(); };
  return (
    <Section title={t('图像生成')} desc={t('给「AI 科研插图生成」技能用：机制示意图、图形摘要、封面图。任选一家 OpenAI 兼容的图像接口，填地址、模型名和密钥；不填就不启用（数据图表不需要它，智能体用 matplotlib 画）。')}>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {IMAGE_PRESETS.map((p) => <button key={p.name} className={'btn ' + (cur.imageBaseUrl === p.base ? 'btn-tint' : 'btn-ghost')} title={p.hint} onClick={() => setD({ imageBaseUrl: p.base, imageModel: p.model, imageApiKey: cur.imageApiKey })}>{p.name}</button>)}
      </div>
      <div className="flex flex-col gap-2">
        <input className="field t-mono" placeholder={t('接口地址，例如 https://open.bigmodel.cn/api/paas/v4')} value={cur.imageBaseUrl} onChange={(e) => setD((x) => ({ ...x, imageBaseUrl: e.target.value }))} />
        <div className="flex gap-2">
          <input className="field t-mono flex-1" placeholder={t('模型名')} value={cur.imageModel} onChange={(e) => setD((x) => ({ ...x, imageModel: e.target.value }))} />
          <input className="field t-mono flex-1" type="password" placeholder={t('密钥')} value={cur.imageApiKey} onChange={(e) => setD((x) => ({ ...x, imageApiKey: e.target.value }))} />
        </div>
        <div className="flex items-center gap-3">
          <button className="btn btn-primary" disabled={Object.keys(d).length === 0} onClick={save}>{saved ? t('已保存') : t('保存并重启智能体')}</button>
          {settings.imageBaseUrl && <span className="t-caption">{t('已启用：在对话里说「帮我画一张 … 的示意图」即可')}</span>}
        </div>
      </div>
    </Section>
  );
}

const MCP_PRESETS: { name: string; server: McpServer; hint: string }[] = [
  { name: 'Zotero (zotero-mcp)', hint: '通过 MCP 直接读写 Zotero 文献库（需要 Zotero 开着并启用本地 API）', server: { name: 'zotero', transport: 'stdio', command: 'uv', args: ['tool', 'run', 'zotero-mcp', 'serve'], env: { ZOTERO_LOCAL: 'true' } } },
  { name: '文件系统', hint: '让智能体读写指定文件夹（官方 filesystem 服务）', server: { name: 'files', transport: 'stdio', command: 'npx', args: ['-y', '@modelcontextprotocol/server-filesystem', '.'] } },
  { name: 'PubMed', hint: '社区 PubMed 检索服务（pubmedmcp）', server: { name: 'pubmed', transport: 'stdio', command: 'uv', args: ['tool', 'run', 'pubmedmcp'] } },
  { name: 'HTTP 服务', hint: '自建/云端的 Streamable HTTP MCP 服务', server: { name: 'remote', transport: 'streamable-http', url: 'http://localhost:3000/mcp' } },
];

/** MCP 接入：每个服务写成 dsh 的一个 mcp-client 插件实例，工具名 mcp__<name>__<tool> */
function McpSection() {
  const { settings, updateSettings, restartDsh } = useApp();
  const { t } = useT();
  const [list, setList] = useState<McpServer[] | null>(null);
  const [dirty, setDirty] = useState(false);
  if (!settings) return null;
  const cur = list ?? settings.mcpServers ?? [];
  const set = (next: McpServer[]) => { setList(next); setDirty(true); };
  const upd = (i: number, p: Partial<McpServer>) => set(cur.map((m, j) => (j === i ? { ...m, ...p } : m)));
  const save = async () => { await updateSettings({ mcpServers: cur.filter((m) => m.name.trim()) }); setList(null); setDirty(false); void restartDsh(); };
  return (
    <Section title={t('MCP 接入')} desc={t('把外部工具服务（MCP）接给智能体：Zotero、PubMed、文件系统、课题组自建服务……接上后智能体多出一批工具，名字以 mcp_服务名 开头。改完要重启智能体。')}>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {MCP_PRESETS.map((p) => <button key={p.name} className="btn btn-ghost" title={p.hint} onClick={() => set([...cur, { ...p.server, args: [...(p.server.args ?? [])], env: { ...(p.server.env ?? {}) } }])}>+ {p.name}</button>)}
      </div>
      {cur.length === 0 && <div className="t-caption" style={{ color: 'var(--text-3)' }}>{t('还没有接入任何 MCP 服务。点上面的预设加一个，或自己填命令。')}</div>}
      <div className="flex flex-col gap-2">
        {cur.map((m, i) => (
          <div key={i} className="p-3 rounded-xl flex flex-col gap-2" style={{ background: 'var(--surface-2)' }}>
            <div className="flex items-center gap-2">
              <input className="field t-mono !w-[140px]" placeholder={t('名称（字母数字）')} value={m.name} onChange={(e) => upd(i, { name: e.target.value.replace(/[^A-Za-z0-9_-]/g, '') })} />
              <div className="seg">
                {(['stdio', 'streamable-http'] as const).map((k) => <button key={k} className={m.transport === k ? 'active' : ''} onClick={() => upd(i, { transport: k })}>{k === 'stdio' ? t('本机命令') : 'HTTP'}</button>)}
              </div>
              <label className="flex items-center gap-1.5 t-caption ml-auto"><input type="checkbox" checked={m.enabled !== false} onChange={(e) => upd(i, { enabled: e.target.checked })} /> {t('启用')}</label>
              <button className="btn btn-ghost" onClick={() => set(cur.filter((_, j) => j !== i))}>{t('删除')}</button>
            </div>
            {m.transport === 'streamable-http'
              ? <input className="field t-mono" placeholder="http://…/mcp" value={m.url ?? ''} onChange={(e) => upd(i, { url: e.target.value })} />
              : <div className="flex gap-2">
                  <input className="field t-mono !w-[160px]" placeholder={t('命令，如 uv / npx')} value={m.command ?? ''} onChange={(e) => upd(i, { command: e.target.value })} />
                  <input className="field t-mono flex-1" placeholder={t('参数，空格分隔')} value={(m.args ?? []).join(' ')} onChange={(e) => upd(i, { args: e.target.value.split(/\s+/).filter(Boolean) })} />
                </div>}
            {m.transport !== 'streamable-http' && <input className="field t-mono" placeholder={t('环境变量（可选）：KEY=value KEY2=value2')} value={Object.entries(m.env ?? {}).map(([k, v]) => `${k}=${v}`).join(' ')} onChange={(e) => upd(i, { env: Object.fromEntries(e.target.value.split(/\s+/).filter((x) => x.includes('=')).map((x) => [x.slice(0, x.indexOf('=')), x.slice(x.indexOf('=') + 1)])) })} />}
          </div>
        ))}
      </div>
      <div className="flex items-center gap-3 mt-3">
        <button className="btn btn-primary" disabled={!dirty} onClick={save}>{t('保存并重启智能体')}</button>
        <span className="t-caption" style={{ color: 'var(--text-3)' }}>{t('本机命令会在智能体的环境里运行：自带的 uv / npx 都可用；uv tool run 会自动下载对应的 Python 包。')}</span>
      </div>
    </Section>
  );
}

/** 示范项目：随软件附带的 4 个真实项目 */
function DemosSection() {
  const { t } = useT();
  const { refreshSessions, restartDsh } = useApp() as unknown as { refreshSessions?: () => void; restartDsh: () => Promise<unknown> };
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    try { const r = await window.biodsh.demosSeed(); setMsg(t('已安装 {n} 个示范项目，正在重启智能体以恢复附带的对话…', { n: String(r.length) })); refreshSessions?.(); void restartDsh(); }
    catch (e) { setMsg(String(e).slice(0, 120)); }
    setBusy(false);
  };
  return (
    <Section title={t('示范项目')} desc={t('软件自带 4 个真实项目：单细胞分析与作图、文献调研、公共数据库抓取、电脑控制与 Zotero。每个项目里有数据、当时的完整对话记录（示范对话.md）和产出，可以照着提问。首次启动已自动装好；误删了可在这里重新安装（不会覆盖你改过的文件）。')}>
      <div className="flex items-center gap-3">
        <button className="btn btn-tint" disabled={busy} onClick={run}><RefreshCw size={13} className={busy ? 'animate-spin' : ''} /> {t('重新安装示范项目')}</button>
        {msg && <span className="t-caption">{msg}</span>}
      </div>
    </Section>
  );
}
