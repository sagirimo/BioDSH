// Approved Sky identity, 2026-10-18. Keep the brand/ folder beside react/.
import lightWordmark from '../brand/wordmark-light.svg';
import darkWordmark from '../brand/wordmark-dark.svg';
import lightApp from '../brand/app-light-rounded.svg';
import darkApp from '../brand/app-dark-rounded.svg';
import lightSmall from '../brand/app-light-small.svg';
import darkSmall from '../brand/app-dark-small.svg';
export function BioBrand({ variant = 'wordmark', theme = 'light', size = 140, className }: {
  variant?: 'wordmark' | 'app'; theme?: 'light' | 'dark'; size?: number; className?: string;
}) {
  const dark = theme === 'dark';
  const src = variant === 'wordmark' ? (dark ? darkWordmark : lightWordmark)
    : size <= 32 ? (dark ? darkSmall : lightSmall) : (dark ? darkApp : lightApp);
  return <img src={src} width={size} alt="BioDSH" className={className}
    style={{ display: 'block', height: variant === 'app' ? size : 'auto', objectFit: 'contain' }} draggable={false} />;
}
