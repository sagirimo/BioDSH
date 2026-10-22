// 轻量 Markdown 渲染，够显示 SKILL.md：标题、段落、有序/无序列表、代码块、引用、表格、分隔线，
// 行内代码 / 粗体 / 斜体 / 链接。图片按工作区相对路径无法加载，显示为说明文字。不渲染原始 HTML。
import React from 'react';

function inline(s: string, keyBase = 0): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\))/g;
  let last = 0, m: RegExpExecArray | null, k = keyBase;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    const t = m[0];
    if (t.startsWith('`')) out.push(<code key={k++}>{t.slice(1, -1)}</code>);
    else if (t.startsWith('**')) out.push(<strong key={k++}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith('![')) { const alt = t.slice(2, t.indexOf(']')); out.push(<span key={k++} className="t-caption">［{alt || '图'}］</span>); }
    else if (t.startsWith('[')) {
      const label = t.slice(1, t.indexOf(']')); const href = t.slice(t.indexOf('(') + 1, -1);
      out.push(/^https?:\/\//.test(href)
        ? <a key={k++} href={href} onClick={(e) => { e.preventDefault(); void window.biodsh.openExternal(href); }} style={{ color: 'var(--accent)' }}>{label}</a>
        : <span key={k++} style={{ color: 'var(--text-2)' }}>{label}</span>);
    } else out.push(<em key={k++}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/^---\n[\s\S]*?\n---\n/, '').split(/\r?\n/);
  const nodes: React.ReactNode[] = [];
  let i = 0, k = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf: string[] = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; nodes.push(<pre key={k++}><code>{buf.join('\n')}</code></pre>); continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { const lvl = Math.min(h[1].length + 1, 4); nodes.push(React.createElement(`h${lvl}`, { key: k++ }, inline(h[2]))); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { nodes.push(<hr key={k++} style={{ border: 0, borderTop: '1px solid var(--border)', margin: '14px 0' }} />); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(line); i += 2; const body: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) body.push(cells(lines[i++]));
      nodes.push(<div key={k++} style={{ overflowX: 'auto', borderRadius: 10, boxShadow: '0 0 0 1px var(--border)', margin: '8px 0' }}><table><thead><tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead><tbody>{body.map((r, a) => <tr key={a}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ''));
      nodes.push(<blockquote key={k++}>{inline(buf.join(' '))}</blockquote>); continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line); const items: string[] = [];
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, ''));
      const Tag = ordered ? 'ol' : 'ul';
      nodes.push(<Tag key={k++}>{items.map((it, j) => <li key={j}>{inline(it.replace(/^\[[ x]\]\s*/i, ''))}</li>)}</Tag>); continue;
    }
    if (!line.trim()) { i++; continue; }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>|\s*([-*+]|\d+[.)])\s|\s*\|)/.test(lines[i])) buf.push(lines[i++]);
    if (!buf.length) { buf.push(lines[i++]); }
    nodes.push(<p key={k++}>{inline(buf.join(' '))}</p>);
  }
  return <div className="md">{nodes}</div>;
}
