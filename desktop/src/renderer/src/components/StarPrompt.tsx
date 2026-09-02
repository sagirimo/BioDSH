// 每次打开 BioDSH 都提示去 GitHub 点 Star（首次引导里已有 Star 步骤，故 onboarded 后才显示）。
// 用户点「已经点过了，不再提示」会永久关闭；点「稍后」只关本次，下次启动仍会提示。
import { useEffect, useState } from 'react';
import { Star, X, ExternalLink } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';

const REPO = 'https://github.com/sagirimo/BioDSH';
const DONE_KEY = 'biodsh.star.done';

export default function StarPrompt() {
  const { settings, pushOverlay, popOverlay } = useApp();
  const { t } = useT();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!settings?.onboarded) return;              // 首次引导已有 Star 步骤，不重复打扰
    let done = false;
    try { done = localStorage.getItem(DONE_KEY) === '1'; } catch { /* ignore */ }
    if (done) return;
    const timer = setTimeout(() => setShow(true), 1200); // 每次启动都提示
    return () => clearTimeout(timer);
  }, [settings?.onboarded]);

  // 浮层出现时把 dsh 子 webview 移开，否则原生层会盖住这个弹窗
  useEffect(() => { if (!show) return; pushOverlay(); return () => popOverlay(); }, [show, pushOverlay, popOverlay]);

  if (!show) return null;
  const neverAgain = () => { try { localStorage.setItem(DONE_KEY, '1'); } catch { /* ignore */ } setShow(false); };
  const later = () => setShow(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.4)' }} onClick={later}>
      <div className="card w-[440px] p-8 flex flex-col items-center text-center no-drag rise" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-ghost !h-6 !px-2 self-end -mt-2 -mr-2" onClick={later} aria-label={t('稍后')}><X size={14} /></button>
        <span className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}><Star size={26} /></span>
        <div className="t-title1 mt-4">{t('给 BioDSH 点个 Star ⭐')}</div>
        <p className="t-body mt-2 max-w-[360px]" style={{ color: 'var(--text-2)' }}>
          {t('BioDSH 完全免费开源。在 GitHub 上点一个 Star，是对我们最大的鼓励，也能让更多同行看到它。')}
        </p>
        <div className="w-full mt-4 rounded-xl p-3.5 text-left t-body" style={{ background: 'var(--surface-2)', color: 'var(--text-2)', fontSize: 13, lineHeight: '24px' }}>
          {t('① 点下面的按钮打开 GitHub 页面')}<br />
          {t('② 点页面右上角那个 ⭐ Star 按钮（需要 GitHub 账号，没有就顺手注册一个）')}
        </div>
        <button className="btn btn-primary btn-lg mt-5" onClick={() => window.biodsh.openExternal(REPO)}><ExternalLink size={15} /> {t('去 GitHub 点 Star')}</button>
        <div className="flex gap-4 mt-3">
          <button className="btn btn-ghost" onClick={later}>{t('稍后')}</button>
          <button className="btn btn-ghost" onClick={neverAgain} style={{ color: 'var(--text-3)' }}>{t('已经点过了，不再提示')}</button>
        </div>
      </div>
    </div>
  );
}
