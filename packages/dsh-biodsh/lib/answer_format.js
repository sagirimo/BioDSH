// Conservative serialization only. Never infer units or percentage conversion from an answer value.
const DIGITS = Object.fromEntries(Array.from('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻').map((c,i)=>[c,'0123456789+-'[i]]));
export function normalizeAnswer(text, { unit = '', bareNumber = false } = {}) {
  const lines = String(text).trimEnd().split(/\r?\n/);
  const index = lines.length - 1;
  const m = lines[index].match(/^\s*ANSWER\s*:\s*(.*?)\s*$/i);
  if (!m) return { text, value: null, changed: false, reason: 'no-terminal-answer' };
  const original = m[1];
  let value = original.replace(/([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[×x*·]\s*10(?:\^\s*([+-]?\d+)|([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+))/g,
    (_, base, ascii, sup) => `${base}e${ascii ?? Array.from(sup).map(c=>DIGITS[c]).join('')}`);
  value = value.replace(/(^|\s)10([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)/g, (_, lead, sup)=>`${lead}1e${Array.from(sup).map(c=>DIGITS[c]).join('')}`);
  // Strip only a caller-confirmed requested unit, only when a bare numeric answer was explicitly requested.
  if (bareNumber && unit && !/[%％]/.test(unit) && value.endsWith(unit)) {
    const candidate = value.slice(0,-unit.length).trim();
    if (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(candidate)) value=candidate;
  }
  lines[index] = 'ANSWER: ' + value;
  const normalized = lines.join('\n');
  return { text: normalized, value, changed: normalized !== text, reason: value === original ? 'preserved-units-and-scale' : 'lossless-numeric-serialization' };
}
