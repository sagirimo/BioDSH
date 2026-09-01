// 极简 Markdown 渲染（标题/段落/列表/代码块/行内代码/粗体），足够显示 SKILL.md。
import React from 'react';

function inline(s: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0, m: RegExpExecArray | null, k = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    const t = m[0];
    out.push(t.startsWith('`') ? <code key={k++}>{t.slice(1, -1)}</code> : <strong key={k++}>{t.slice(2, -2)}</strong>);
    last = m.index + t.length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split(/\r?\n/);
  const nodes: React.ReactNode[] = [];
  let i = 0, k = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith('```')) {
      const buf: string[] = []; i++;
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++]);
      i++; nodes.push(<pre key={k++}><code>{buf.join('\n')}</code></pre>); continue;
    }
    const h = l.match(/^(#{1,3})\s+(.*)/);
    if (h) { const T = (`h${h[1].length}`) as 'h1' | 'h2' | 'h3'; nodes.push(<T key={k++}>{inline(h[2])}</T>); i++; continue; }
    if (/^\s*[-*]\s+/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ''));
      nodes.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ul>); continue;
    }
    if (/^\s*\d+\.\s+/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, ''));
      nodes.push(<ol key={k++}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>); continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) buf.push(lines[i++]);
    nodes.push(<p key={k++}>{inline(buf.join(' '))}</p>);
  }
  return <div className="md">{nodes}</div>;
}
