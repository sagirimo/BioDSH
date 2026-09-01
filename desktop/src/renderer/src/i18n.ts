// 极简国际化：界面源码里写中文，t('中文') 在英文模式下查表返回英文；查不到就原样返回（并在开发时提示）。
// 语言来自设置 language: 'system' | 'zh' | 'en'。词典在 ./i18n.en.ts。
import { createContext, useContext } from 'react';
import { EN } from './i18n.en';

export type Lang = 'zh' | 'en';
export type LangSetting = Lang | 'system';

export function resolveLang(setting: LangSetting | undefined): Lang {
  if (setting === 'zh' || setting === 'en') return setting;
  const nav = typeof navigator !== 'undefined' ? navigator.language.toLowerCase() : 'zh';
  return nav.startsWith('zh') ? 'zh' : 'en';
}

const missing = new Set<string>();
export function translate(lang: Lang, zh: string, vars?: Record<string, string | number>): string {
  let out = zh;
  if (lang === 'en') {
    const hit = EN[zh];
    if (hit) out = hit;
    else if (import.meta.env.DEV && !missing.has(zh)) { missing.add(zh); console.warn('[i18n] missing en:', zh); }
  }
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
  return out;
}

export const LangContext = createContext<Lang>('zh');
export function useT() {
  const lang = useContext(LangContext);
  return { lang, t: (zh: string, vars?: Record<string, string | number>) => translate(lang, zh, vars) };
}
