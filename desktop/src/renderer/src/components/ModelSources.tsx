import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';
import { BioIcon } from '../icons';

// 模型来源：记住多个模型接口（中转站、各家云厂商、课题组自建 vLLM / Ollama），随时切换默认模型。
// 不自己存配置：读写的是 dsh 0.2 官方「模型」设置页同一套数据（llm-pi-ai.providers + agent-default-model），
// 密钥经 credentials/set 只写进 dsh 凭据库，配置文件里只有引用名。对话框里的模型选择器（官方插件）也能按任务临时切换。
interface NsView { ns: string; value: Record<string, unknown>; user: Record<string, unknown>; revision?: number }
interface Route { displayName?: string; api?: string; baseURL?: string; apiKeyEnv?: string; models?: { id: string; name?: string }[] }
interface ProviderInfo { id: string; name: string }
interface Discovered { id: string; name?: string }

const API_LABEL: Record<string, string> = { 'openai-completions': 'OpenAI Chat Completions', 'openai-responses': 'OpenAI Responses', 'anthropic-messages': 'Anthropic Messages' };
// 常见 OpenAI 兼容来源：只帮忙填地址，模型列表用「获取可用模型」从接口实时读取。
const PRESETS: { id: string; label: string; base: string; api?: string }[] = [
  { id: 'openrouter', label: 'OpenRouter', base: 'https://openrouter.ai/api/v1' },
  { id: 'siliconflow', label: '硅基流动 SiliconFlow', base: 'https://api.siliconflow.cn/v1' },
  { id: 'qwen', label: '通义千问 DashScope', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'moonshot', label: 'Moonshot Kimi', base: 'https://api.moonshot.cn/v1' },
  { id: 'zhipu', label: '智谱 GLM', base: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'ollama', label: 'Ollama（本机）', base: 'http://localhost:11434/v1' },
  { id: 'vllm', label: 'vLLM / 自建服务', base: 'http://192.168.1.10:8000/v1' },
];
const OFFLINE_ROUTE = 'biodsh-offline';
const slug = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
const keyRef = (id: string) => `${id.toUpperCase().replace(/-/g, '_')}_API_KEY`;

export default function ModelSources() {
  const { dsh } = useApp();
  const { t } = useT();
  const rpc = useCallback((ep: string, args: unknown) => window.biodsh.dshRpc(`raw:${ep}`, args), []);
  const [pi, setPi] = useState<NsView | null>(null);
  const [adm, setAdm] = useState<NsView | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [keys, setKeys] = useState<Record<string, boolean>>({});
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    if (dsh.state !== 'running') return;
    try {
      const desc = await rpc('settings/describe', {}) as { namespaces: NsView[] };
      const p = desc.namespaces.find((n) => n.ns === 'llm-pi-ai') ?? null;
      setPi(p); setAdm(desc.namespaces.find((n) => n.ns === 'agent-default-model') ?? null);
      setProviders(await rpc('llm/listProviders', {}) as ProviderInfo[]);
      const refs = Object.values((p?.value.providers ?? {}) as Record<string, Route>).map((r) => r.apiKeyEnv).filter((x): x is string => !!x);
      if (refs.length) setKeys(Object.fromEntries(Object.entries(await rpc('credentials/describe', { refs }) as Record<string, { configured: boolean }>).map(([k, v]) => [k, v.configured])));
    } catch (e) { setMsg({ ok: false, text: t('读取模型来源失败：{msg}', { msg: String(e).slice(0, 120) }) }); }
  }, [dsh.state, rpc]);
  useEffect(() => { void load(); }, [load]);

  const routes = (pi?.value.providers ?? {}) as Record<string, Route>;
  const userRoutes = (pi?.user.providers ?? {}) as Record<string, Route>;
  const def = (adm?.value ?? {}) as { provider?: string; model?: string };
  const flash = (ok: boolean, text: string) => { setMsg({ ok, text }); setTimeout(() => setMsg(null), 5000); };

  const setDefault = async (provider: string, model: string) => {
    try {
      const ops: unknown[] = [{ op: 'set', path: ['provider'], value: provider }, { op: 'set', path: ['model'], value: model }];
      // 推理强度是按模型的能力；换到别家模型时去掉 DeepSeek 的 high，交给该模型默认值
      if (provider !== 'deepseek-official') ops.push({ op: 'unset', path: ['reasoningEffort'] });
      await rpc('settings/mutate', { ns: 'agent-default-model', ops, expectedRevision: adm?.revision });
      flash(true, t('新任务将默认使用 {model}', { model })); await load();
    } catch (e) { flash(false, t('保存失败：{msg}', { msg: String(e).slice(0, 120) })); }
  };
  const remove = async (id: string) => {
    if (!window.confirm(t('删除模型来源「{name}」？已保存的密钥也会一起删除。', { name: routes[id]?.displayName ?? id }))) return;
    try {
      const ref = userRoutes[id]?.apiKeyEnv;
      await rpc('settings/mutate', { ns: 'llm-pi-ai', ops: [{ op: 'unset', path: ['providers', id] }], expectedRevision: pi?.revision });
      if (ref === keyRef(id)) await rpc('credentials/unset', { ref }).catch(() => undefined);
      if (def.provider === id) await setDefault('deepseek-official', 'deepseek-flash');
      flash(true, t('已删除')); await load();
    } catch (e) { flash(false, t('删除失败：{msg}', { msg: String(e).slice(0, 120) })); }
  };

  const deepseekModels = useMemo(() => ['deepseek-flash', 'deepseek-v4-pro'], []);
  if (dsh.state !== 'running') return <div className="t-caption">{t('智能体启动后才能管理模型来源。')}</div>;

  return (
    <div className="flex flex-col gap-2.5">
      <SourceRow name={providers.find((p) => p.id === 'deepseek-official')?.name ?? 'DeepSeek'} detail={t('官方接口 · 密钥在下方「模型 API Key」')} models={deepseekModels} provider="deepseek-official" def={def} onDefault={setDefault} builtIn />
      {Object.entries(routes).map(([id, r]) => (
        <SourceRow key={id} name={r.displayName ?? id} provider={id} def={def} onDefault={setDefault}
          detail={[r.baseURL, r.api && API_LABEL[r.api], id === OFFLINE_ROUTE ? t('由「运行模式」管理') : r.apiKeyEnv ? (keys[r.apiKeyEnv] ? t('密钥已保存') : t('密钥未保存')) : t('无密钥')].filter(Boolean).join(' · ')}
          models={(r.models ?? []).map((m) => m.id)} onRemove={id !== OFFLINE_ROUTE && userRoutes[id] ? () => void remove(id) : undefined} />
      ))}
      {adding ? <AddSource existing={Object.keys(routes)} rpc={rpc} revision={pi?.revision} onDone={(saved) => { setAdding(false); if (saved) { flash(true, t('已添加「{name}」', { name: saved })); void load(); } }} />
        : <div><button className="btn btn-line" onClick={() => setAdding(true)}><Plus size={13} />{t('添加模型来源')}</button></div>}
      {msg && <div className="t-caption" role="status" style={{ color: msg.ok ? 'var(--green)' : 'var(--red)' }}>{msg.text}</div>}
    </div>
  );
}

function SourceRow({ name, detail, models, provider, def, onDefault, onRemove, builtIn }: {
  name: string; detail: string; models: string[]; provider: string; def: { provider?: string; model?: string };
  onDefault: (provider: string, model: string) => void; onRemove?: () => void; builtIn?: boolean;
}) {
  const { t } = useT();
  const active = def.provider === provider;
  return (
    <div className="src-row" data-active={active || undefined}>
      <BioIcon name={builtIn ? 'ui-source-official' : provider === OFFLINE_ROUTE ? 'ui-offline' : 'ui-database'} size={18} style={{ color: active ? 'var(--accent)' : 'var(--text-3)' }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><span style={{ fontWeight: 500 }}>{name}</span>{active && <span className="pill pill-on">{t('默认')}</span>}</div>
        <div className="t-caption truncate mono" title={detail}>{detail}</div>
      </div>
      <select className="field !h-8 !w-auto mono" style={{ maxWidth: 220, fontSize: 12 }} aria-label={t('默认模型')} value={active ? def.model ?? '' : ''} onChange={(e) => e.target.value && onDefault(provider, e.target.value)} disabled={models.length === 0}>
        <option value="">{models.length ? t('设为默认…') : t('没有模型')}</option>
        {models.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
      {onRemove && <button className="icon-btn" title={t('删除')} aria-label={t('删除')} onClick={onRemove}><Trash2 size={14} /></button>}
    </div>
  );
}

function AddSource({ existing, rpc, revision, onDone }: { existing: string[]; rpc: (ep: string, args: unknown) => Promise<unknown>; revision?: number; onDone: (saved: string | null) => void }) {
  const { t } = useT();
  const [name, setName] = useState('');
  const [base, setBase] = useState('');
  const [api, setApi] = useState('openai-completions');
  const [key, setKey] = useState('');
  const [models, setModels] = useState('');
  const [found, setFound] = useState<Discovered[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const id = slug(name) || slug(base.replace(/^https?:\/\//, ''));
  const idTaken = existing.includes(id) || id === 'deepseek-official' || id === 'deepseek-account';
  const urlOk = /^https?:\/\/[^\s/]+/i.test(base.trim());
  const modelList = [...new Set([...picked, ...models.split(/[\s,，]+/).map((s) => s.trim()).filter(Boolean)])];

  const discover = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await rpc('llm/discoverModels', { settingsNs: 'llm-pi-ai', request: { baseURL: base.trim(), api, ...(key.trim() ? { apiKey: key.trim() } : {}) } }) as Discovered[];
      setFound(r); if (r.length === 0) setErr(t('接口没有返回模型列表，请手动填写模型名。'));
    } catch (e) { setErr(t('获取失败：{msg}', { msg: String(e).slice(0, 160) })); } finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const route: Route = { displayName: name.trim() || id, api, baseURL: base.trim(), models: modelList.map((m) => ({ id: m, name: found?.find((f) => f.id === m)?.name ?? m })) };
      if (key.trim()) { route.apiKeyEnv = keyRef(id); await rpc('credentials/set', { ref: route.apiKeyEnv, value: key.trim() }); }
      await rpc('settings/mutate', { ns: 'llm-pi-ai', ops: [{ op: 'set', path: ['providers', id], value: route }], expectedRevision: revision });
      onDone(route.displayName ?? id);
    } catch (e) { setErr(t('保存失败：{msg}', { msg: String(e).slice(0, 160) })); setBusy(false); }
  };

  return (
    <div className="card-flat flex flex-col gap-3" style={{ padding: '14px 16px' }}>
      <div className="flex items-center justify-between"><span style={{ fontWeight: 500 }}>{t('添加模型来源')}</span><button className="icon-btn" aria-label={t('关闭')} onClick={() => onDone(null)}><X size={14} /></button></div>
      <select className="field" value="" aria-label={t('常用来源')} onChange={(e) => { const p = PRESETS.find((x) => x.id === e.target.value); if (p) { setName(p.label.split(/[（(]/)[0].trim()); setBase(p.base); setApi(p.api ?? 'openai-completions'); setFound(null); } }}>
        <option value="">{t('从常用来源填入…')}</option>
        {PRESETS.map((p) => <option key={p.id} value={p.id}>{t(p.label)}</option>)}
      </select>
      <div className="flex gap-3">
        <label className="flex-1 flex flex-col gap-1.5"><span className="t-caption">{t('名称')}</span><input className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder={t('例如：课题组服务器')} /></label>
        <label className="flex-1 flex flex-col gap-1.5"><span className="t-caption">{t('接口协议')}</span>
          <select className="field" value={api} onChange={(e) => setApi(e.target.value)}>{Object.entries(API_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      </div>
      <label className="flex flex-col gap-1.5"><span className="t-caption">{t('接口地址')}</span><input className="field mono" value={base} onChange={(e) => setBase(e.target.value)} placeholder={api === 'anthropic-messages' ? 'https://gateway.example' : 'https://gateway.example/v1'} /></label>
      <label className="flex flex-col gap-1.5"><span className="t-caption">{t('API Key（本机自建服务可留空）')}</span><input className="field mono" type="password" autoComplete="new-password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-…" /></label>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between"><span className="t-caption">{t('模型')}</span><button className="btn btn-ghost !h-7" disabled={!urlOk || busy} onClick={discover}>{busy ? t('读取中…') : t('获取可用模型')}</button></div>
        {found && found.length > 0 && (
          <div className="model-pick">{found.map((m) => (
            <label key={m.id} title={m.name ?? m.id}><input type="checkbox" checked={picked.has(m.id)} onChange={(e) => setPicked((s) => { const n = new Set(s); if (e.target.checked) n.add(m.id); else n.delete(m.id); return n; })} /><span className="mono">{m.id}</span></label>
          ))}</div>
        )}
        <input className="field mono" value={models} onChange={(e) => setModels(e.target.value)} placeholder={t('也可以手动填写，多个用逗号分隔')} />
      </div>
      {err && <div className="t-caption" style={{ color: 'var(--red)' }}>{err}</div>}
      {idTaken && <div className="t-caption" style={{ color: 'var(--orange)' }}>{t('已有同名来源，请换个名称')}</div>}
      <div className="flex items-center gap-2">
        <button className="btn btn-primary" disabled={busy || !id || idTaken || !urlOk || modelList.length === 0} onClick={save}>{t('保存')}</button>
        <span className="t-caption">{t('密钥只保存在本机 dsh 凭据库，不写进配置文件。')}</span>
      </div>
    </div>
  );
}
