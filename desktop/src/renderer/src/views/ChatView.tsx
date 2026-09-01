import { useEffect, useRef } from 'react';
import { RefreshCw, Play, AlertTriangle } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';

// 对话页本身不渲染聊天：它只留出一块区域，主进程把 dsh 的网页视图贴在这块区域上。
export default function ChatView() {
  const { dsh, startDsh, restartDsh, credential, setTab, env, settings, overlay } = useApp();
  const { t } = useT();
  const overlayOpen = !settings?.onboarded || overlay > 0;
  const areaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (dsh.state === 'stopped') void startDsh();
  }, []);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const report = () => {
      const r = el.getBoundingClientRect();
      window.biodsh.dshBounds({ x: r.left, y: r.top, width: r.width, height: r.height }, dsh.state === 'running' && !overlayOpen);
    };
    report();
    const ro = new ResizeObserver(report);
    ro.observe(el);
    window.addEventListener('resize', report);
    return () => { ro.disconnect(); window.removeEventListener('resize', report); window.biodsh.dshBounds({ x: 0, y: 0, width: 0, height: 0 }, false); };
  }, [dsh.state, overlayOpen]);

  return (
    <div className="h-full flex flex-col">
      <header className="drag h-[52px] flex items-center justify-between pl-5 pr-0 hairline-b" style={{ background: 'var(--bg)' }}>
        <div className="flex items-center gap-3">
          <span className="t-title2">{t('对话')}</span>
          {!credential.hasKey && (
            <button className="no-drag badge" style={{ color: 'var(--orange)', background: 'rgba(255,159,10,.14)' }} onClick={() => setTab('settings')}><AlertTriangle size={12} /> {t('还没填 API Key')}</button>
          )}
          {!env.ready && (
            <button className="no-drag badge" onClick={() => setTab('env')}>{t('分析环境未就绪')}</button>
          )}
        </div>
        <div className="flex items-center gap-1 pr-2 no-drag">
          <button className="btn btn-ghost" title={t('重新加载页面')} onClick={() => window.biodsh.dshReload()}><RefreshCw size={14} /></button>
          <button className="btn btn-ghost" onClick={() => restartDsh()}>{t('重启智能体')}</button>
          
        </div>
      </header>
      <div ref={areaRef} className="flex-1 min-h-0 relative" style={{ background: 'var(--surface)' }}>
        {dsh.state !== 'running' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 rise">
            {dsh.state === 'starting' && <><div className="ring spin" style={{ ['--p' as string]: 30 }} /><div className="t-body" style={{ color: 'var(--text-2)' }}>{t('正在启动智能体…')}</div></>}
            {dsh.state === 'error' && (
              <>
                <div className="t-title2">{t('智能体没能启动')}</div>
                <div className="t-body max-w-[420px] text-center" style={{ color: 'var(--text-2)' }}>{dsh.error}</div>
                <button className="btn btn-primary" onClick={() => restartDsh()}><Play size={13} /> {t('再试一次')}</button>
                <pre className="log max-w-[640px] max-h-[220px] mt-2">{dsh.log.slice(-40).join('\n')}</pre>
              </>
            )}
            {dsh.state === 'stopped' && <button className="btn btn-primary btn-lg" onClick={() => startDsh()}><Play size={14} /> {t('启动智能体')}</button>}
          </div>
        )}
      </div>
    </div>
  );
}
