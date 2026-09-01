// 应用内自动更新：查 GitHub Releases 的 latest.json → 下载 → 校验签名 → 安装 → 重启。
import { useState } from 'react';
import { RefreshCw, Download } from 'lucide-react';
import { useT } from '../i18n';

type S = { kind: 'idle' } | { kind: 'checking' } | { kind: 'none'; version: string } | { kind: 'available'; version: string; notes?: string } | { kind: 'downloading'; pct: number } | { kind: 'done' } | { kind: 'error'; msg: string };

export default function UpdateCheck({ currentVersion }: { currentVersion?: string }) {
  const { t } = useT();
  const [s, setS] = useState<S>({ kind: 'idle' });
  const isTauri = window.biodsh?.mode === 'tauri';

  const check = async () => {
    setS({ kind: 'checking' });
    try {
      if (!isTauri) { setS({ kind: 'error', msg: t('Electron 版不支持应用内更新') }); return; }
      const { check } = await import('@tauri-apps/plugin-updater');
      const u = await check();
      if (!u) { setS({ kind: 'none', version: currentVersion ?? '' }); return; }
      setS({ kind: 'available', version: u.version, notes: u.body ?? undefined });
      (window as unknown as { __biodshUpdate?: unknown }).__biodshUpdate = u;
    } catch (e) { setS({ kind: 'error', msg: String(e).slice(0, 160) }); }
  };
  const install = async () => {
    const u = (window as unknown as { __biodshUpdate?: { downloadAndInstall: (cb: (ev: { event: string; data: { contentLength?: number; chunkLength?: number } }) => void) => Promise<void> } }).__biodshUpdate;
    if (!u) return;
    let total = 0, got = 0;
    setS({ kind: 'downloading', pct: 0 });
    try {
      await u.downloadAndInstall((ev) => {
        if (ev.event === 'Started') total = ev.data.contentLength ?? 0;
        else if (ev.event === 'Progress') { got += ev.data.chunkLength ?? 0; setS({ kind: 'downloading', pct: total ? Math.round((got / total) * 100) : 0 }); }
        else if (ev.event === 'Finished') setS({ kind: 'done' });
      });
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    } catch (e) { setS({ kind: 'error', msg: String(e).slice(0, 160) }); }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button className="btn btn-ghost" onClick={check} disabled={s.kind === 'checking' || s.kind === 'downloading'}><RefreshCw size={13} className={s.kind === 'checking' ? 'spin' : ''} /> {t('检查更新')}</button>
      {s.kind === 'checking' && <span className="t-caption">{t('正在检查…')}</span>}
      {s.kind === 'none' && <span className="t-caption" style={{ color: 'var(--green)' }}>{t('已是最新版本')}{s.version ? ` v${s.version}` : ''}</span>}
      {s.kind === 'available' && <>
        <span className="t-caption" style={{ color: 'var(--orange)' }}>{t('发现新版本 v{v}', { v: s.version })}</span>
        <button className="btn btn-primary" onClick={install}><Download size={13} /> {t('下载并安装，然后重启')}</button>
      </>}
      {s.kind === 'downloading' && <span className="t-caption">{t('下载中 {p}%', { p: s.pct })}</span>}
      {s.kind === 'done' && <span className="t-caption">{t('安装完成，正在重启…')}</span>}
      {s.kind === 'error' && <span className="t-caption" style={{ color: 'var(--red)' }}>{s.msg}</span>}
    </div>
  );
}
