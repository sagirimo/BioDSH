import { useEffect, useState } from 'react';

// App.tsx 把解析后的主题写在 <html data-theme>（系统设置已换算成 light/dark）；品牌图要用这个值，不能用设置里的 'system'。
const read = (): 'light' | 'dark' => (document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');

export function useResolvedTheme(): 'light' | 'dark' {
  const [theme, setTheme] = useState(read);
  useEffect(() => {
    const ob = new MutationObserver(() => setTheme(read()));
    ob.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => ob.disconnect();
  }, []);
  return theme;
}
