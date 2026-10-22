import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Play, RotateCcw } from 'lucide-react';
import { BioIcon } from '../icons';
import { useApp } from '../store';
import { useT } from '../i18n';
import { TopBar } from '../components/Chrome';

// 任务页：上面是我们的细标题栏（路径、状态、存为工作流、审阅结论），下面这块区域由主进程贴上 dsh 的对话视图。
export default function ChatView() {
  const { dsh, startDsh, restartDsh, credential, setTab, settings, overlay, taskMeta } = useApp();
  const { t } = useT();
  const overlayOpen = !settings?.onboarded || overlay > 0;
  const areaRef = useRef<HTMLDivElement>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => { if (dsh.state === 'stopped') void startDsh(); }, []);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const report = () => {
      const r = el.getBoundingClientRect();
      window.biodsh.dshBounds({ x: r.left, y: r.top, width: r.width, height: r.height }, dsh.state === 'running' && !overlayOpen);
    };
    report();
    const ro = new ResizeObserver(report);
    ro.observe(el);
    window.addEventListener('resize', report);
    return () => { ro.disconnect(); window.removeEventListener('resize', report); window.biodsh.dshBounds({ x: 0, y: 0, width: 0, height: 0 }, false); };
  }, [dsh.state, overlayOpen]);

  const send = async (text: string, ok: string) => {
    if (!taskMeta) return;
    try { await window.biodsh.dshRpc('session.prompt', { sessionId: taskMeta.sessionId, mode: 'queue', content: [{ type: 'text', text }] }); setNotice(ok); }
    catch (e) { setNotice(t('发送失败：{msg}', { msg: String(e).slice(0, 80) })); }
    setTimeout(() => setNotice(null), 3500);
  };
  const review = () => send(t('请以独立审稿人的身份审阅你在本任务里给出的最终结论。逐条列出每个结论及其依据（对应的文件、表格或数值），标注：证据充分 / 证据不足 / 有问题，并说明理由。检查统计单位、多重检验、对照与混杂、样本量和数据质量。最后用一段话说明哪些问题会改变结论、哪些只影响表述。不要修改任何文件。'), t('已请求审阅，结果会出现在对话里'));
  const toPipeline = () => send(t('/pipeline-builder 请把本任务整理成一条可复现的工作流。先列出你从本任务里提取到的实际执行步骤，等我确认保留哪些、哪些参数开放给新数据，再问我要哪些验证选项，最后写入项目的 pipelines 文件夹并做一次复现验证。'), t('已开始构建工作流，按对话里的提示确认步骤'));

  const busyTask = !!taskMeta?.running;
  return (
    <div className="h-full flex flex-col">
      <TopBar actions={
        <>
          {notice && <span className="pill pill-on rise">{notice}</span>}
          {!credential.hasKey && <button className="btn btn-ghost" style={{ color: 'var(--orange)' }} onClick={() => setTab('settings')}><BioIcon name="ui-warning" size={14} /> {t('还没填 API Key')}</button>}
          {taskMeta && !taskMeta.blank && <>
            <button className="btn btn-ghost" onClick={review} disabled={busyTask} title={busyTask ? t('任务运行中，结束后再审阅') : undefined}><BioIcon name="ui-review" size={15} />{t('审阅结论')}</button>
            <button className="btn btn-line" onClick={toPipeline} disabled={busyTask}><BioIcon name="ui-save-workflow" size={15} />{t('存为工作流')}</button>
          </>}
          <button className="icon-btn" title={t('重新加载对话区')} aria-label={t('重新加载对话区')} onClick={() => window.biodsh.dshReload()}><RefreshCw size={14} /></button>
          <button className="icon-btn" title={t('重启智能体')} aria-label={t('重启智能体')} onClick={() => restartDsh()}><RotateCcw size={14} /></button>
        </>
      }>
        {taskMeta ? <>
          <span className="truncate" style={{ maxWidth: 220 }}>{taskMeta.project}</span><span>/</span>
          <span className="cur">{taskMeta.title}</span>
          <span className={`pill ${taskMeta.running ? 'pill-run' : 'pill-off'}`} title={!taskMeta.running && !taskMeta.blank ? t('任务已停止运行；结论是否正确请用「审阅结论」核对') : undefined}>{taskMeta.running ? t('运行中') : taskMeta.blank ? t('新任务') : t('已结束')}</span>
        </> : <span className="cur">{t('任务')}</span>}
      </TopBar>
      <div ref={areaRef} className="flex-1 min-h-0 relative" style={{ background: 'var(--bg)' }}>
        {dsh.state !== 'running' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 rise">
            {dsh.state === 'starting' && <><BioIcon name="ui-agent-running" size={34} className="bds-spin" style={{ color: 'var(--accent)' }} /><div className="t-body" style={{ color: 'var(--text-2)' }}>{t('正在启动智能体…')}</div></>}
            {dsh.state === 'error' && (
              <>
                <div className="serif" style={{ fontSize: 20 }}>{t('智能体没能启动')}</div>
                <div className="t-body max-w-[420px] text-center" style={{ color: 'var(--text-2)' }}>{dsh.error}</div>
                <button className="btn btn-primary" onClick={() => restartDsh()}><Play size={13} /> {t('再试一次')}</button>
                <pre className="log max-w-[640px] max-h-[220px] mt-2">{dsh.log.slice(-40).join('\n')}</pre>
              </>
            )}
            {dsh.state === 'stopped' && <button className="btn btn-primary btn-lg" onClick={() => startDsh()}><Play size={14} /> {t('启动智能体')}</button>}
          </div>
        )}
      </div>
    </div>
  );
}
