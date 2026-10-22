// 统一图标：晴蓝品牌包（assets/biodsh-ui）的 BioIcon，对外接口保持不变。
import { BioIcon, type BioIconName } from './assets/biodsh-ui/react/BioIcon';
import { CATEGORY_ICONS, DOMAIN_ICONS, FILE_ICONS, PACK_ICONS, fileIconFor } from './assets/biodsh-ui/react/mappings';

export { BioIcon, fileIconFor };
export type { BioIconName };

export function FileTypeIcon({ type, name, size = 18 }: { type: string; name?: string; size?: number }) {
  return <BioIcon name={name ? fileIconFor(type, name) : FILE_ICONS[type] ?? 'file-generic'} size={size} />;
}
export function PackIcon({ name, size = 26 }: { name: string; size?: number }) {
  return <BioIcon name={PACK_ICONS[name] ?? 'domain-data-tools'} size={size} />;
}
export function DomainIcon({ domain, size = 16 }: { domain: string; size?: number }) {
  return <BioIcon name={DOMAIN_ICONS[domain] ?? 'domain-data-tools'} size={size} />;
}
export function SkillIcon({ category, domain, size = 20 }: { category?: string; domain?: string; size?: number }) {
  const name = (category ? CATEGORY_ICONS[category] : undefined) ?? (domain ? DOMAIN_ICONS[domain] : undefined) ?? 'domain-data-tools';
  return <BioIcon name={name} size={size} />;
}
