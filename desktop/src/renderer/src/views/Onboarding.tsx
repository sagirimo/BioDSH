import { useState } from 'react';
import { ArrowRight, Check, ExternalLink } from 'lucide-react';
import { useApp } from '../store';
import { Logo } from '../components/Sidebar';
import { useT } from '../i18n';

// 首次启动的三步引导：欢迎 → 填 API Key → 安装分析环境。全屏居中卡片，可跳过。
export default function Onboarding() {
  const { updateSettings, saveKey, credential, env, installEnv, setTab } = useApp();
  const { t } = useT();
  const [step, setStep] = useState(0);
  const [key, setKey] = useState('');
  const installing = ['python', 'venv', 'packages', 'verify'].includes(env.step);
  const finish = async (goStore = true) => { await updateSettings({ onboarded: true }); setTab(goStore ? 'store' : 'chat'); };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center drag" style={{ background: 'var(--bg)' }}>
      <div className="card w-[520px] p-10 flex flex-col items-center text-center no-drag rise" key={step}>
        {step === 0 && (
          <>
            <Logo size={72} />
            <div className="t-largetitle mt-6">{t('欢迎使用 BioDSH')}</div>
            <p className="t-body mt-3 max-w-[400px]" style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: '21px' }}>
              {t('用白话让智能体帮你做生信分析。技能商店里的每个技能都在本机离线运行、结果可复现，你的数据不会离开这台电脑。')}
            </p>
            <button className="btn btn-primary btn-lg mt-8" onClick={() => setStep(1)}>{t('开始')} <ArrowRight size={15} /></button>
          </>
        )}
        {step === 1 && (
          <>
            <div className="t-caption">{t('第 1 步 / 共 2 步')}</div>
            <div className="t-title1 mt-2">{t('连接模型')}</div>
            <p className="t-body mt-2" style={{ color: 'var(--text-2)' }}>{t('填入 DeepSeek API Key。之后也可以在「设置」里改。')}</p>
            <input className="field t-mono mt-6 text-center" type="password" autoFocus placeholder={credential.hasKey ? t('已设置 {masked}', { masked: credential.masked ?? '' }) : 'sk-…'} value={key} onChange={(e) => setKey(e.target.value)} />
            <button className="btn btn-ghost mt-2" onClick={() => window.biodsh.openExternal('https://platform.deepseek.com/api_keys')}><ExternalLink size={13} /> {t('还没有？去 DeepSeek 开放平台申请')}</button>
            <div className="flex gap-3 mt-6">
              <button className="btn btn-fill btn-lg" onClick={() => setStep(2)}>{credential.hasKey ? t('下一步') : t('先跳过')}</button>
              <button className="btn btn-primary btn-lg" disabled={!key.trim()} onClick={async () => { await saveKey(key); setStep(2); }}>{t('保存并继续')} <ArrowRight size={15} /></button>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="t-caption">{t('第 2 步 / 共 2 步')}</div>
            <div className="t-title1 mt-2">{t('准备分析环境')}</div>
            <p className="t-body mt-2 max-w-[400px]" style={{ color: 'var(--text-2)' }}>
              {t('技能依赖一套 Python 分析软件包（scanpy 等）。只需安装一次，约需几分钟，期间可以先去逛商店。')}
            </p>
            <div className="w-full mt-6 rounded-xl p-4 text-left" style={{ background: 'var(--surface-2)' }}>
              {env.ready ? (
                <div className="flex items-center gap-2 t-body"><span className="w-5 h-5 rounded-full flex items-center justify-center" style={{ background: 'var(--green)', color: '#fff' }}><Check size={12} strokeWidth={3} /></span>{t('环境已就绪 · Python {v}', { v: env.pythonVersion ?? '' })}</div>
              ) : installing ? (
                <>
                  <div className="t-body">{env.message}</div>
                  <div className="mt-2 h-[6px] rounded-full overflow-hidden" style={{ background: 'var(--fill)' }}><div className="h-full rounded-full transition-all" style={{ width: `${Math.round(env.progress * 100)}%`, background: 'var(--accent)' }} /></div>
                </>
              ) : env.step === 'error' ? (
                <div className="t-body" style={{ color: 'var(--red)' }}>{env.message}</div>
              ) : (
                <div className="t-body" style={{ color: 'var(--text-2)' }}>{t('安装位置：~/BioDSH/bioenv（不影响系统 Python）')}</div>
              )}
            </div>
            <div className="flex gap-3 mt-6">
              {!env.ready && !installing && <button className="btn btn-primary btn-lg" onClick={() => installEnv()}>{env.step === 'error' ? t('重试安装') : t('开始安装')}</button>}
              <button className={`btn btn-lg ${env.ready ? 'btn-primary' : 'btn-fill'}`} onClick={() => finish(true)}>{env.ready ? t('进入商店') : t('稍后再装，先逛商店')} <ArrowRight size={15} /></button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
