import { app } from 'electron';
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { appendFileSync, writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import type { AppPaths, DshStatus } from '../shared/types';
import { venvBinDir, venvPython, nodeBinary, uvBinary } from './paths';
import { migrateCredentials } from './settings';

const require = createRequire(import.meta.url);

// 找到 @deepseek-ai/dsh 的可执行入口 lib/bin.js（打包后位于 app.asar.unpacked）。
function dshBin(): string {
  if (app.isPackaged) return path.join(process.resourcesPath, 'dsh', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
  return path.join(path.dirname(require.resolve('@deepseek-ai/dsh/package.json')), 'lib', 'bin.js');
}

export function setDshTheme(paths: AppPaths, theme: string): void {
  const f = path.join(paths.dshHome, 'settings.yaml');
  const txt = existsSync(f) ? readFileSync(f, 'utf8') : '';
  const out: string[] = []; let skip = false;
  for (const line of txt.split(/\r?\n/)) {
    if (line.startsWith('ui-theme:')) { skip = true; continue; }
    if (skip) { if (/^[ \t]/.test(line) || !line.trim()) continue; skip = false; }
    out.push(line);
  }
  while (out.length && !out[out.length - 1].trim()) out.pop();
  out.push('ui-theme:', `  preference: ${theme}`);
  writeFileSync(f, out.join('\n') + '\n');
}

const PERSONA = "You are BioDSH (中文名同样叫 BioDSH), the built-in bioinformatics assistant of the BioDSH desktop app, powered by the {{model}} model. Your users are doctors and wet-lab scientists with NO programming or bioinformatics background. Your working directory (their project folder) is {{cwd}}.\n\nIdentity: when greeted or asked who you are / what you can do, introduce yourself as BioDSH 生信助手 and give 3 concrete examples they can ask, e.g. 「帮我看看这份单细胞数据的质量」「比较有效和无效病人的细胞组成差异」「解读这个结果文件夹」. Never call yourself a generic coding agent.\n\nYou also know the BioDSH app itself and answer how-to questions about it:\n- 左侧栏「数据」: files in the workspace grouped by type; each file has a 让智能体分析 button; finished analyses appear as result cards with figure thumbnails and a 让智能体解读 button.\n- 「技能商店」: 5 official skills (evaluated, offline, reproducible) plus 2,000+ community skills in Chinese categories; click 获取 to install; rate installed skills 👍/👎 in the detail page.\n- 「分析环境」: one-click Python environment (scanpy etc.); skills need it installed once.\n- 「更多」(settings): DeepSeek API key, workspace folder, 在线/纯离线模式 (offline mode uses a local/intranet model endpoint or a lab Linux dsh server), language 中文/English, theme, version & update check.\n- Right-click anywhere in the app: a \"问一下\" popup explains what things are; right-click a chat in the left sidebar to pin/rename/archive/export; right-click a project for git 版本快照.\n- Data safety: everything runs locally; original data files are never modified; each analysis writes into a new subfolder.\nIf asked about an app detail you are not sure of, say so and point to the closest page instead of inventing UI.\n\nHow you work on analyses:\n- Reply in the language the user writes in. Plain language first, technical detail second; briefly explain any format/tool/statistic you mention.\n- Installed skills are listed for you; when a task matches one, use it and follow its SKILL.md. `python` on PATH is the BioDSH analysis environment (scanpy, anndata, pandas, matplotlib); `uv pip install <pkg>` adds extras.\n- Keep original data untouched; write outputs to a new subfolder and tell the user its name.\n- When a decision is needed (thresholds, which group is control), ask one clear question instead of guessing.";

export function setDshLocale(paths: AppPaths, language: string): void {
  const lang = language === 'en' ? 'en' : language === 'zh' ? 'zh' : (app.getLocale().toLowerCase().startsWith('zh') ? 'zh' : 'en');
  const f = path.join(paths.dshHome, 'settings.yaml');
  const txt = existsSync(f) ? readFileSync(f, 'utf8') : '';
  const out: string[] = []; let skip = false;
  for (const line of txt.split(/\r?\n/)) {
    if (line.startsWith('locale:')) { skip = true; continue; }
    if (skip) { if (/^[ \t]/.test(line) || !line.trim()) continue; skip = false; }
    out.push(line);
  }
  while (out.length && !out[out.length - 1].trim()) out.pop();
  out.push('locale:', `  preference: ${lang}`);
  writeFileSync(f, out.join('\n') + '\n');
}

export function setDshLlmOverride(paths: AppPaths, offline: { baseUrl: string; model: string } | null): void {
  const f = path.join(paths.dshHome, 'settings.yaml');
  const txt = existsSync(f) ? readFileSync(f, 'utf8') : '';
  const out: string[] = []; let skip = false;
  for (const line of txt.split(/\r?\n/)) {
    if (line.startsWith('llm-deepseek:')) { skip = true; continue; }
    if (skip) { if (/^[ \t]/.test(line) || !line.trim()) continue; skip = false; }
    out.push(line);
  }
  while (out.length && !out[out.length - 1].trim()) out.pop();
  if (offline) {
    out.push('llm-deepseek:', `  baseURL: ${offline.baseUrl}`, '  apiKeyEnv: BIODSH_OFFLINE_KEY');
    if (offline.model) out.push('  models:', `    - id: ${offline.model}`, `      name: ${offline.model}`);
  }
  writeFileSync(f, out.join('\n') + '\n');
}

export class DshManager {
  private proc: ChildProcess | null = null;
  status: DshStatus = { state: 'stopped', log: [] };
  constructor(private paths: AppPaths, private onChange: (s: DshStatus) => void) {}

  private push(line: string) {
    try { appendFileSync(path.join(this.paths.logs, 'dsh.log'), `${new Date().toISOString()} ${line}\n`); } catch { /* 忽略 */ }
    this.status.log.push(line);
    if (this.status.log.length > 400) this.status.log.splice(0, this.status.log.length - 400);
  }
  private emit() { this.onChange({ ...this.status, log: [...this.status.log] }); }

  // 精简模式：通过 dsh 自己的补丁层关掉一问一答用不到的界面插件；写默认设置；预置工作区，用户打开就能直接提问。
  private ensureHome(workspace: string) {
    const home = this.paths.dshHome;
    // biodsh 预设：预设层人设覆盖全局人设，必须在预设里替换
    let presetOk = false;
    try {
      const req = createRequire(import.meta.url);
      const std = path.join(path.dirname(req.resolve('@deepseek-ai/dsh/package.json')), 'config', 'agent-presets', 'standard', 'agent.cordis.yml');
      const src = readFileSync(std, 'utf8');
      const coding = '      You are a coding agent powered by the {{model}} model. Your working directory is {{cwd}}.';
      if (src.includes(coding)) {
        const personaYaml = PERSONA.split('\n').map((l) => (l ? `      ${l}` : '')).join('\n');
        const dir = path.join(home, '.agent-presets', 'biodsh');
        mkdirSync(dir, { recursive: true });
        writeFileSync(path.join(dir, 'agent.cordis.yml'), `# biodsh-preset v1 — 由 BioDSH 桌面版自动生成（每次启动重建，请勿手改）\n${src.replace(coding, personaYaml)}`);
        writeFileSync(path.join(dir, 'preset.yml'), 'name: BioDSH 生信助手\ndescription: 面向医生与湿实验科学家的生信分析助手（BioDSH 桌面版默认）。\norder: 0\n');
        presetOk = true;
      }
    } catch { /* 预设生成失败则维持 standard */ }

    const patch = path.join(home, 'cordis.patch.yml');
    if (!existsSync(patch) || /# biodsh-minimal v[1234]/.test(readFileSync(patch, 'utf8'))) {
      const body = ['ui-workflow-run', 'ui-deliverables', 'ui-jobs', 'ui-goal', 'ui-plan', 'ui-trajectory', 'ui-subagent', 'ui-settings-plugin-inventory', 'ui-settings-plugins', 'ui-cordis', 'ui-brand-official', 'ui-message-feedback', 'ui-reference', 'ui-agent-preset', 'ui-sidebar'].map((id) => `- id: ${id}\n  disabled: true`);
      const personaYaml = PERSONA.split('\n').map((l) => (l ? `      ${l}` : '')).join('\n');
      body.push(`- id: system-prompt\n  config:\n    persona: >-\n${personaYaml}`);
      if (presetOk) body.push('- id: agent-presets\n  config:\n    default: biodsh');
      writeFileSync(patch, `# biodsh-minimal v4 — BioDSH 精简模式 + BioDSH 人设（删除本文件并重启即可恢复 dsh 默认）\n${body.join('\n')}\n`);
    }
    const settings = path.join(home, 'settings.yaml');
    if (!existsSync(settings)) {
      writeFileSync(settings, 'ui-onboarding:\n  welcomeNoticeVersion: 2026-08-13.1\nlocale:\n  preference: zh\nui-theme:\n  preference: system\n');
    }
  }

  async start(workspace: string, offlineKey?: string): Promise<DshStatus> {
    if (this.proc) return this.status;
    try { this.ensureHome(workspace); migrateCredentials(this.paths); } catch (e) { this.push(`[ensureHome] ${String(e)}`); }
    this.status = { state: 'starting', log: [] };
    this.emit();
    const bin = dshBin();
    const binDir = venvBinDir(this.paths.bioenv);
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
      DSH_HOME: this.paths.dshHome,
      BIODSH_HOME: this.paths.root,
      BIODSH_PYTHON: venvPython(this.paths.bioenv),
      // 把生信环境放到 PATH 最前面：模型执行 `python run.py` 时用的就是它。
      PATH: `${binDir}${path.delimiter}${path.dirname(uvBinary())}${path.delimiter}${process.env.PATH ?? ''}`,
      UV_PROJECT_ENVIRONMENT: path.join(this.paths.bioenv, '.venv'),
      VIRTUAL_ENV: path.join(this.paths.bioenv, '.venv'),
      DSH_TELEMETRY_DISABLED: '1',
    };
    if (offlineKey !== undefined) env.BIODSH_OFFLINE_KEY = offlineKey;
    delete env.ELECTRON_RUN_AS_NODE;
    const node = nodeBinary();
    if (!existsSync(node)) {
      this.status = { state: 'error', error: `找不到自带的 Node 运行时：${node}`, log: this.status.log };
      this.emit();
      return this.status;
    }
    try {
      this.push(`[spawn] ${node} --expose-internals ${bin} web (cwd ${workspace})`);
      this.proc = spawn(node, ['--expose-internals', bin, 'web', '--port', '0', '--no-open'], {
        cwd: workspace,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      });
    } catch (e) {
      this.status = { state: 'error', error: String(e), log: this.status.log };
      this.emit();
      return this.status;
    }
    const onData = (chunk: Buffer) => {
      for (const line of chunk.toString().split(/\r?\n/)) {
        if (!line.trim()) continue;
        this.push(line);
        const m = line.match(/https?:\/\/127\.0\.0\.1:\d+\S*/);
        if (m && this.status.state === 'starting') {
          this.status = { ...this.status, state: 'running', url: m[0] };
        }
        this.emit();
      }
    };
    this.proc.stdout?.on('data', onData);
    this.proc.stderr?.on('data', onData);
    this.proc.on('error', (e) => { this.push(`[spawn error] ${e.message}`); });
    this.proc.on('exit', (code) => {
      this.push(`[dsh exited with code ${code}]`);
      this.proc = null;
      this.status = { ...this.status, state: this.status.state === 'running' && code === 0 ? 'stopped' : 'error', error: code ? `dsh 退出，代码 ${code}` : undefined };
      this.emit();
    });
    // 等待 URL 出现（最多 60 秒）
    const deadline = Date.now() + 60_000;
    while (this.status.state === 'starting' && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 200));
    }
    if (this.status.state === 'starting') {
      this.status = { ...this.status, state: 'error', error: 'dsh 启动超时（60 秒内未就绪）' };
      this.emit();
    }
    return this.status;
  }

  async restart(workspace: string): Promise<DshStatus> {
    await this.stop();
    return this.start(workspace);
  }

  async stop(): Promise<void> {
    if (!this.proc) return;
    const p = this.proc;
    this.proc = null;
    p.kill();
    if (process.platform === 'win32' && p.pid) { try { spawn('taskkill', ['/pid', String(p.pid), '/T', '/F'], { windowsHide: true }); } catch { /* 忽略 */ } }
    await new Promise((r) => setTimeout(r, 300));
    this.status = { state: 'stopped', log: this.status.log };
    this.emit();
  }
}

app.on('will-quit', () => { /* utilityProcess 随主进程退出 */ });
