import { Award } from 'lucide-react';
import { useApp } from '../store';
import { useT } from '../i18n';
import type { CatalogSkill } from '@shared/types';

// 技能全量可用：不再有「安装/打开」。这里展示技能的可信度信号——官方技能显示评分，社区技能标「未评测」。
export default function InstallButton({ skill, size = 'sm' }: { skill: CatalogSkill; size?: 'sm' | 'lg' }) {
  const { setTab } = useApp();
  const { t } = useT();
  const big = size === 'lg';
  if (typeof skill.score === 'number') {
    const c = skill.score >= 85 ? 'var(--green)' : skill.score >= 70 ? 'var(--accent)' : 'var(--text-2)';
    return (
      <span className="score-chip" style={{ color: c, borderColor: c, fontSize: big ? 15 : 12, padding: big ? '4px 12px' : '2px 9px' }} title={skill.score_source ?? t('BioDSH 评测（五维加权：正确性/鲁棒性/可复现/离线/效率）')}>
        <Award size={big ? 15 : 12} /> {skill.score}
        <span style={{ opacity: 0.6, fontWeight: 400 }}>{big ? ' 分' : ''}</span>
      </span>
    );
  }
  return <button className={big ? 'btn btn-ghost' : 'btn btn-ghost !h-6 !px-2'} style={{ color: 'var(--text-3)' }} onClick={() => setTab('chat')} title={t('社区技能，尚未经 BioDSH 评测；需要时智能体会自动调用')}>{t('未评测')}</button>;
}
