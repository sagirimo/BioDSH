import { useCallback, useEffect, useState } from 'react';
import { useApp } from '../store';
import { useT } from '../i18n';

// BioDSH-MAGI（Multi-Analyst Gated Inspection）：读写 dsh 设置里 BioDSH 的 Host 行（ns: biodsh）的 magiMode，
// 和插件 lib/settings.js 是同一份数据，改了下一轮任务就生效，不用重启智能体。
type Mode = 'off' | 'adaptive' | 'always';
interface NsView { ns: string; value: Record<string, unknown>; revision?: number }

export default function MagiMode() {
  const { dsh } = useApp();
  const { t } = useT();
  const rpc = useCallback((ep: string, args: unknown) => window.biodsh.dshRpc(`raw:${ep}`, args), []);
  const [ns, setNs] = useState<NsView | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (dsh.state !== 'running') return;
    try {
      const desc = await rpc('settings/describe', {}) as { namespaces: NsView[] };
      setNs(desc.namespaces.find((n) => n.ns === 'biodsh') ?? null);
    } catch (e) { setMsg(t('读取失败：{msg}', { msg: String(e).slice(0, 120) })); }
  }, [dsh.state, rpc, t]);
  useEffect(() => { void load(); }, [load]);
  if (dsh.state !== 'running') return <div className="t-caption">{t('智能体启动后才能设置。')}</div>;
  if (!ns) return <div className="t-caption">{t('当前智能体版本不支持 MAGI。')}</div>;
  const mode = ((ns.value.magiMode as Mode | undefined) ?? 'off');
  const set = async (m: Mode) => {
    try {
      await rpc('settings/mutate', { ns: 'biodsh', ops: [{ op: 'set', path: ['magiMode'], value: m }], expectedRevision: ns.revision });
      setMsg(t('已保存，下一个任务生效')); setTimeout(() => setMsg(null), 3000); await load();
    } catch (e) { setMsg(t('保存失败：{msg}', { msg: String(e).slice(0, 120) })); }
  };
  const options: { id: Mode; label: string }[] = [
    { id: 'off', label: t('关闭（默认）') },
    { id: 'adaptive', label: t('自适应') },
    { id: 'always', label: t('每次都复核') },
  ];
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {options.map((o) => <button key={o.id} className={'btn ' + (mode === o.id ? 'btn-tint' : 'btn-ghost')} onClick={() => mode !== o.id && void set(o.id)}>{o.label}</button>)}
      {msg && <span className="t-caption ml-2">{msg}</span>}
    </div>
  );
}
