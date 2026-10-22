import type React from 'react';
import { Minus, Square, X } from 'lucide-react';
import { useApp, type Tab } from '../store';
import { useT } from '../i18n';
import { BioIcon, type BioIconName } from '../icons';
import { BioBrand } from '../assets/biodsh-ui/react/BioBrand';
import { NAV_ICONS } from '../assets/biodsh-ui/react/mappings';
import { useResolvedTheme } from '../theme';

// 左侧图标导航栏：项目 / 技能 / 工作流 / 数据库，底部帮助与设置。
export function Rail() {
  const { tab, setTab, info, env } = useApp();
  const { t } = useT();
  const theme = useResolvedTheme();
  const isMac = info?.platform === 'darwin';
  const item = (id: Tab, label: string, icon: BioIconName, dot?: string | null) => (
    <button className={`rail-btn no-drag relative ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)} aria-current={tab === id}>
      <span className="ic"><BioIcon name={icon} size={21} /></span>{label}
      {dot && <span className="rail-dot" style={{ background: dot }} />}
    </button>
  );
  const envDot = env.step === 'error' ? 'var(--red)' : null;
  return (
    <nav className="rail drag" aria-label={t('主导航')} style={isMac ? { paddingTop: 34 } : undefined}>
      <div className="rail-logo"><BioBrand variant="app" theme={theme} size={40} /></div>
      {item('chat', t('项目'), NAV_ICONS.chat)}
      {item('skills', t('技能'), NAV_ICONS.skills)}
      {item('pipes', t('工作流'), NAV_ICONS.pipes)}
      {item('db', t('数据库'), NAV_ICONS.db)}
      <div className="rail-grow" />
      <button className="rail-btn no-drag" onClick={() => void window.biodsh.openExternal('https://github.com/sagirimo/BioDSH#readme')}><span className="ic"><BioIcon name={NAV_ICONS.help} size={21} /></span>{t('帮助')}</button>
      {item('settings', t('设置'), NAV_ICONS.settings, envDot)}
    </nav>
  );
}

// 主区顶栏：左边放标题/路径，右边放操作；整条可拖动窗口，Windows 上带窗口按钮。
export function TopBar({ children, actions }: { children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="topbar drag">
      <div className="crumb">{children}</div>
      <div className="flex items-center gap-1.5 no-drag">{actions}<WindowControls compact /></div>
    </header>
  );
}

export function WindowControls({ compact = false }: { compact?: boolean }) {
  const { info } = useApp();
  if (info?.platform === 'darwin') return null;
  const size = compact ? 'w-[40px] h-[52px]' : 'w-[46px] h-[44px]';
  const b = (a: 'minimize' | 'maximize' | 'close', I: typeof Minus) => (
    <button className={`no-drag ${size} flex items-center justify-center hover:bg-[var(--fill)]`} onClick={() => window.biodsh.windowControl(a)} aria-label={a}><I size={13} strokeWidth={1.5} /></button>
  );
  return <div className="flex" style={{ color: 'var(--text-2)' }}>{b('minimize', Minus)}{b('maximize', Square)}{b('close', X)}</div>;
}
