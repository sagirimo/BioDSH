// 右键"问一下"：在任何地方右键，弹出一个小窗——模型选项 + 问题框（灰字提示"这是干什么的？"）+ 发送。
// 回答直接来自 DeepSeek，带上当前页面和鼠标所指内容作为上下文，让不熟悉的人也能边用边学。
import { useEffect, useRef, useState } from 'react';
import { Send, X, Sparkles } from 'lucide-react';
import { useApp } from '../store';
import Markdown from './Markdown';
import { useT, translate, type Lang } from '../i18n';

const TAB_NAME: Record<string, string> = { chat: '对话页', store: '技能商店', env: '分析环境页', settings: '设置页' };
const MODELS = [{ id: 'deepseek-chat', label: 'DeepSeek 快速' }, { id: 'deepseek-reasoner', label: 'DeepSeek 深思' }];

interface Anchor { x: number; y: number; context: string; hint: string }

function describeTarget(el: Element | null, lang: Lang): { context: string; hint: string } {
  const t = (zh: string, vars?: Record<string, string | number>) => translate(lang, zh, vars);
  let node: Element | null = el;
  while (node && node !== document.body) {
    const help = node.getAttribute('data-help') ?? node.getAttribute('title') ?? node.getAttribute('aria-label');
    if (help) return { context: help, hint: t('「{x}」是干什么的？', { x: help.slice(0, 20) }) };
    node = node.parentElement;
  }
  const text = (el?.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 160);
  return { context: text || t('（空白处）'), hint: text ? t('「{x}」是什么意思？', { x: `${text.slice(0, 16)}${text.length > 16 ? '…' : ''}` }) : t('这个页面是干什么用的？') };
}

export default function AskPopover() {
  const { tab, settings, pushOverlay, popOverlay } = useApp();
  const { t, lang } = useT();
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [model, setModel] = useState(MODELS[0].id);
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onMenu = (e: MouseEvent) => {
      if (e.defaultPrevented) return; // 行级菜单已处理
      e.preventDefault();
      if (!settings?.onboarded) return;
      const d = describeTarget(e.target as Element, lang);
      const x = Math.min(e.clientX, window.innerWidth - 380), y = Math.min(e.clientY, window.innerHeight - 220);
      setAnchor({ x, y, context: `${TAB_NAME[tab] ? t(TAB_NAME[tab]) : tab} · ${d.context}`, hint: d.hint });
      setQ(''); setAnswer('');
      setTimeout(() => inputRef.current?.focus(), 30);
    };
    const onDown = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setAnchor(null); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setAnchor(null); };
    const onAsk = (e: Event) => { const d = (e as CustomEvent).detail as { x: number; y: number; context: string; hint: string }; setAnchor({ x: Math.min(d.x, window.innerWidth - 380), y: Math.min(d.y, window.innerHeight - 220), context: d.context, hint: d.hint }); setQ(''); setAnswer(''); setTimeout(() => inputRef.current?.focus(), 30); };
    window.addEventListener('biodsh:ask', onAsk);
    window.addEventListener('contextmenu', onMenu);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('biodsh:ask', onAsk); window.removeEventListener('contextmenu', onMenu); window.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey); };
  }, [tab, settings?.onboarded, lang]);

  useEffect(() => { if (!anchor) return; pushOverlay(); return () => popOverlay(); }, [anchor, pushOverlay, popOverlay]);
  if (!anchor) return null;
  const send = async () => {
    const question = q.trim() || anchor.hint;
    setLoading(true); setAnswer('');
    try { setAnswer(String(await window.biodsh.assistantAsk(model, question, anchor.context))); }
    catch (e) { setAnswer(t('出错了：{msg}', { msg: String(e).replace(/^Error: /, '') })); }
    finally { setLoading(false); }
  };
  return (
    <div ref={boxRef} className="fixed z-[60] w-[360px] card rise" style={{ left: anchor.x, top: anchor.y, boxShadow: 'var(--shadow-sheet)' }} onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}>
      <div className="flex items-center gap-2 px-3 pt-2.5 pb-1.5">
        <Sparkles size={13} style={{ color: 'var(--accent)' }} />
        <select className="field !h-[24px] !w-auto !text-[12px] !py-0 !rounded-md" value={model} onChange={(e) => setModel(e.target.value)}>
          {MODELS.map((m) => <option key={m.id} value={m.id}>{t(m.label)}</option>)}
        </select>
        <span className="t-caption truncate flex-1" title={anchor.context}>{anchor.context.slice(0, 28)}</span>
        <button className="p-1 rounded-md hover:bg-black/5" onClick={() => setAnchor(null)}><X size={13} /></button>
      </div>
      <div className="px-3 pb-3 flex items-center gap-2">
        <input ref={inputRef} className="field flex-1" placeholder={anchor.hint} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && !loading && send()} />
        <button className="btn btn-primary !px-3" disabled={loading} onClick={send}>{loading ? <span className="ring spin" style={{ ['--p' as string]: 30, width: 14, height: 14 }} /> : <Send size={14} />}</button>
      </div>
      {(answer || loading) && (
        <div className="px-3 pb-3">
          <div className="rounded-xl px-3 py-2 selectable max-h-[260px] overflow-y-auto" style={{ background: 'var(--surface-2)' }}>{loading ? <span className="t-body">{t('正在想…')}</span> : <Markdown text={answer} />}</div>
        </div>
      )}
    </div>
  );
}
