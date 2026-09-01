import { useApp } from '../store';
import { useT } from '../i18n';
import type { CatalogSkill } from '@shared/types';

export default function InstallButton({ skill, size = 'sm' }: { skill: CatalogSkill; size?: 'sm' | 'lg' }) {
  const { statuses, busy, install, env, setTab } = useApp();
  const { t } = useT();
  const st = statuses[skill.id]?.state ?? 'not_installed';
  const cls = size === 'lg' ? 'btn btn-lg' : 'btn';
  if (busy[skill.id]) return <button className={`${cls} btn-tint`} disabled><span className="ring spin" style={{ ['--p' as string]: 35, width: 14, height: 14 }} /> {t('安装中')}</button>;
  if (st === 'installed') return <button className={`${cls} btn-fill`} onClick={() => setTab('chat')}>{t('打开')}</button>;
  if (st === 'update_available') return <button className={`${cls} btn-primary`} onClick={() => install(skill.id)}>{t('更新')}</button>;
  if (!env.ready) return <button className={`${cls} btn-tint`} onClick={() => install(skill.id)} title={t('安装后需要先准备分析环境')}>{t('获取')}</button>;
  return <button className={`${cls} btn-tint`} onClick={() => install(skill.id)}>{t('获取')}</button>;
}
