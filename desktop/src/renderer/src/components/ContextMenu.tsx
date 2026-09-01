import { useEffect, useRef } from 'react';
import { useApp } from '../store';

export interface MenuItem { label: string; icon?: React.ReactNode; danger?: boolean; disabled?: boolean; onClick: () => void }
export interface MenuState { x: number; y: number; items: (MenuItem | 'sep')[] }

export default function ContextMenu({ menu, onClose }: { menu: MenuState; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const { pushOverlay, popOverlay } = useApp();
  useEffect(() => { pushOverlay(); return () => popOverlay(); }, [pushOverlay, popOverlay]);
  useEffect(() => {
    const down = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('mousedown', down); window.addEventListener('keydown', key);
    return () => { window.removeEventListener('mousedown', down); window.removeEventListener('keydown', key); };
  }, [onClose]);
  const x = Math.min(menu.x, window.innerWidth - 200), y = Math.min(menu.y, window.innerHeight - 40 * menu.items.length - 16);
  return (
    <div ref={ref} className="fixed z-[70] min-w-[176px] max-w-[320px] py-1 rise" style={{ left: x, top: y, background: 'var(--surface)', borderRadius: 10, boxShadow: 'var(--shadow-sheet)' }} onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}>
      {menu.items.map((it, i) => it === 'sep' ? <div key={i} className="my-1 hairline-t" /> : (
        <button key={i} disabled={it.disabled} className="w-full text-left flex items-center gap-2 h-[30px] px-3 t-body hover:bg-[var(--fill)] disabled:opacity-40 whitespace-nowrap" style={{ color: it.danger ? 'var(--red)' : 'var(--text)' }} onClick={() => { onClose(); it.onClick(); }}>
          {it.icon && <span className="w-4 flex justify-center opacity-80">{it.icon}</span>}{it.label}
        </button>
      ))}
    </div>
  );
}
