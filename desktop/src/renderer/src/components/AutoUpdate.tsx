// 自动更新提醒：启动后 + 每隔几小时静默查一次 GitHub Releases 的 latest.json，
// 发现新版本就在右下角弹一条提示，用户点「下载并安装」即可（下载→校验签名→安装→重启）。
// 「稍后」会记住这个版本号，同一版本不再打扰；出下一个版本时会重新提示。
import { useEffect, useRef, useState } from 'react';
import { Download, X, ArrowUpCircle } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';

const FIRST_DELAY = 15_000;            // 启动后 15s 首次检查，不拖慢启动
const CHECK_INTERVAL = 6 * 3600_000;   // 之后每 6 小时查一次

type Avail = { version: string; notes?: string };
type Prog = { kind: 'idle' } | { kind: 'downloading'; pct: number } | { kind: 'done' } | { kind: 'error'; msg: string };
type TauriUpdate = { version: string; body?: string | null; downloadAndInstall: (cb: (ev: { event: string; data: { contentLength?: number; chunkLength?: number } }) => void) => Promise<void> };

const DISMISS_KEY = 'biodsh.update.dismissed';

export default function AutoUpdate() {
  const { settings } = useApp();
  const { t } = useT();
  const [avail, setAvail] = useState<Avail | null>(null);
  const [prog, setProg] = useState<Prog>({ kind: 'idle' });
  const [dismissed, setDismissed] = useState<string | null>(() => { try { return localStorage.getItem(DISMISS_KEY); } catch { return null; } });
  const updRef = useRef<TauriUpdate | null>(null);
  const isTauri = window.biodsh?.mode === 'tauri';
  const offline = settings?.mode === 'offline';

  useEffect(() => {
    if (!isTauri || offline) return;                          // Electron 版与纯离线模式不联网检查
    let stopped = false;
    const run = async () => {
      try {
        const { check } = await import('@tauri-apps/plugin-updater');
        const u = (await check()) as TauriUpdate | null;
        if (stopped || !u) return;
        updRef.current = u;
        setAvail({ version: u.version, notes: u.body ?? undefined });
      } catch { /* 网络/离线错误：忽略，下个周期再试 */ }
    };
    const first = setTimeout(run, FIRST_DELAY);
    const iv = setInterval(run, CHECK_INTERVAL);
    return () => { stopped = true; clearTimeout(first); clearInterval(iv); };
  }, [isTauri, offline]);

  const install = async () => {
    const u = updRef.current;
    if (!u) return;
    let total = 0, got = 0;
    setProg({ kind: 'downloading', pct: 0 });
    try {
      await u.downloadAndInstall((ev) => {
        if (ev.event === 'Started') total = ev.data.contentLength ?? 0;
        else if (ev.event === 'Progress') { got += ev.data.chunkLength ?? 0; setProg({ kind: 'downloading', pct: total ? Math.round((got / total) * 100) : 0 }); }
        else if (ev.event === 'Finished') setProg({ kind: 'done' });
      });
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    } catch (e) { setProg({ kind: 'error', msg: String(e).slice(0, 160) }); }
  };

  const later = () => { try { localStorage.setItem(DISMISS_KEY, avail!.version); } catch { /* ignore */ } setDismissed(avail!.version); };

  // 有可用更新，且（没被本版本忽略 或 正在下载中）才显示
  if (!avail) return null;
  const busy = prog.kind !== 'idle';
  if (!busy && dismissed === avail.version) return null;

  return (
    <div className="auto-update-toast" role="alert">
      <div className="au-icon"><ArrowUpCircle size={18} /></div>
      <div className="au-body">
        <div className="au-title">{t('发现新版本 v{v}', { v: avail.version })}</div>
        {prog.kind === 'idle' && avail.notes && <div className="au-notes">{avail.notes.slice(0, 140)}</div>}
        {prog.kind === 'downloading' && <div className="au-notes">{t('下载中 {p}%', { p: prog.pct })}</div>}
        {prog.kind === 'done' && <div className="au-notes">{t('安装完成，正在重启…')}</div>}
        {prog.kind === 'error' && <div className="au-notes" style={{ color: 'var(--red)' }}>{prog.msg}</div>}
        {prog.kind === 'idle' && (
          <div className="au-actions">
            <button className="btn btn-primary" onClick={install}><Download size={13} /> {t('下载并安装，然后重启')}</button>
            <button className="btn btn-ghost" onClick={later}>{t('稍后')}</button>
          </div>
        )}
      </div>
      {prog.kind === 'idle' && <button className="au-close" onClick={later} aria-label={t('稍后')}><X size={14} /></button>}
    </div>
  );
}
