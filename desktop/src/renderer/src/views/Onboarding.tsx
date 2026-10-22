import { useState } from 'react';
import { ExternalLink, RotateCcw } from 'lucide-react';
import { BioIcon } from '../icons';
import { BioBrand } from '../assets/biodsh-ui/react/BioBrand';
import { useResolvedTheme } from '../theme';
import { useApp } from '../store';
import { useT } from '../i18n';

// 首次启动：只问模型密钥。分析环境在后台自动安装（store 启动时触发），这里只显示进度。
const STEPS: { id: string; label: string }[] = [
  { id: 'python', label: 'Python 3.12 运行时' },
  { id: 'venv', label: '独立的分析环境（不影响电脑上别的软件）' },
  { id: 'packages', label: '分析软件包：scanpy、pandas、statsmodels 等' },
  { id: 'verify', label: '检查安装结果' },
];
const ORDER = ['idle', 'python', 'venv', 'packages', 'verify', 'ready'];

export default function Onboarding() {
  const { updateSettings, saveKey, credential, env, installEnv, setTab } = useApp();
  const { t } = useT();
  const theme = useResolvedTheme();
  const [key, setKey] = useState('');
  const idx = env.ready ? ORDER.length : ORDER.indexOf(env.step);
  const finish = async (tab: 'chat' | 'settings' = 'chat') => { if (key.trim()) await saveKey(key.trim()); await updateSettings({ onboarded: true }); setTab(tab); };

  return (
    <div className="onb-wrap drag">
      <div className="onb-box no-drag rise">
        <div className="onb-brand"><BioBrand variant="wordmark" theme={theme} size={164} />{!env.ready && <BioIcon name={env.step === 'error' ? 'illustrations-connection-needed' : 'illustrations-env-installing'} size={200} className="onb-art" />}</div>
        <div className="eyebrow">{t('欢迎使用 BioDSH 1.0')}</div>
        <h1 className="serif">{t('先填一个模型密钥，其余的我们来准备。')}</h1>
        <p className="sd-lead">{t('分析环境正在后台安装，不用等它装完。装好后，把数据文件夹加为项目，就可以直接用中文提问。')}</p>

        <div className="card" style={{ padding: '16px 18px' }}>
          <div className="flex items-baseline justify-between"><span style={{ fontWeight: 500 }}>{t('分析环境')}</span>
            <span className="mono t-caption">{env.ready ? t('已就绪 · Python {v}', { v: env.pythonVersion ?? '' }) : env.step === 'error' ? t('安装没有成功') : `${Math.round(env.progress * 100)}%`}</span></div>
          <div className="prog"><i style={{ width: `${env.ready ? 100 : Math.round(env.progress * 100)}%`, background: env.step === 'error' ? 'var(--red)' : undefined }} /></div>
          <div className="flex flex-col gap-2 mt-3">
            {STEPS.map((s) => {
              const i = ORDER.indexOf(s.id); const done = idx > i; const now = idx === i && !env.ready;
              return (
                <div key={s.id} className="flex items-center gap-2.5 t-body">
                  {done ? <BioIcon name="ui-check" size={16} style={{ color: 'var(--green)' }} /> : now ? <span className="spin inline-block w-[14px] h-[14px] rounded-full" style={{ border: '2px solid var(--sunk)', borderTopColor: 'var(--text)' }} /> : <span className="inline-block w-[14px] h-[14px] rounded-full" style={{ boxShadow: 'inset 0 0 0 1.5px var(--line)' }} />}
                  <span className="flex-1" style={{ color: done || now ? 'var(--text)' : 'var(--text-3)' }}>{t(s.label)}</span>
                  <span className="mono t-caption">{done ? t('完成') : now ? t('进行中') : t('等待')}</span>
                </div>
              );
            })}
          </div>
          {env.step === 'error' && <div className="flex items-center justify-between gap-3 mt-3"><span className="t-caption" style={{ color: 'var(--red)' }}>{env.message}</span><button className="btn btn-line" onClick={() => installEnv()}><RotateCcw size={13} />{t('重试')}</button></div>}
        </div>

        <div className="flex gap-2 mt-5">
          <input id="onb-key" className="field mono" type="password" autoFocus placeholder={credential.hasKey ? t('已设置 {masked}', { masked: credential.masked ?? '' }) : t('DeepSeek API Key，以 sk- 开头')} value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && (key.trim() || credential.hasKey)) void finish(); }} style={{ height: 40 }} />
          <button className="btn btn-primary" style={{ height: 40, padding: '0 18px' }} disabled={!key.trim() && !credential.hasKey} onClick={() => finish()}>{t('开始使用')}</button>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 t-caption">
          <button className="flex items-center gap-1" style={{ color: 'var(--accent)' }} onClick={() => window.biodsh.openExternal('https://platform.deepseek.com/api_keys')}><ExternalLink size={12} />{t('还没有密钥？去 DeepSeek 开放平台申请')}</button>
          <button style={{ color: 'var(--text-2)' }} onClick={() => finish('settings')}>{t('改用本地或内网模型')}</button>
        </div>
      </div>
    </div>
  );
}
