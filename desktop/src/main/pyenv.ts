import { spawn } from 'node:child_process';
import { existsSync, cpSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import type { AppPaths, EnvStatus } from '../shared/types';
import { uvBinary, venvPython, resourcePath } from './paths';

// 用打包自带的 uv 建 Python 生信环境：下载 Python 3.12 → 建 venv → 按 uv.lock 装包 → 验证。
// 全部落在 ~/BioDSH/bioenv 与 ~/BioDSH/uv，不碰系统 Python。
export class PyEnvManager {
  status: EnvStatus = { ready: false, step: 'idle', message: '尚未安装', progress: 0, log: [] };
  private running = false;
  constructor(private paths: AppPaths, private onChange: (s: EnvStatus) => void) {}

  private set(patch: Partial<EnvStatus>) {
    this.status = { ...this.status, ...patch };
    this.onChange({ ...this.status, log: [...this.status.log] });
  }
  private log(line: string) {
    this.status.log.push(line);
    if (this.status.log.length > 500) this.status.log.splice(0, this.status.log.length - 500);
    this.set({});
  }

  private uvEnv(useChinaMirror: boolean): Record<string, string> {
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
      UV_PYTHON_INSTALL_DIR: path.join(this.paths.root, 'uv', 'python'),
      UV_CACHE_DIR: path.join(this.paths.root, 'uv', 'cache'),
      UV_PROJECT_ENVIRONMENT: path.join(this.paths.bioenv, '.venv'),
      UV_NO_PROGRESS: '1',
      UV_HTTP_TIMEOUT: '120',
    };
    if (useChinaMirror) {
      env.UV_PYTHON_INSTALL_MIRROR = 'https://registry.npmmirror.com/-/binary/python-build-standalone';
      env.UV_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple';
    }
    return env;
  }

  private run(args: string[], env: Record<string, string>, cwd: string, onLine?: (l: string) => void): Promise<number> {
    return new Promise((resolve, reject) => {
      const uv = uvBinary();
      this.log(`$ uv ${args.join(' ')}`);
      const child = spawn(uv, args, { cwd, env, windowsHide: true });
      const handle = (b: Buffer) => {
        for (const l of b.toString().split(/\r?\n/)) { if (l.trim()) { this.log(l); onLine?.(l); } }
      };
      child.stdout.on('data', handle);
      child.stderr.on('data', handle);
      child.on('error', reject);
      child.on('close', (code) => resolve(code ?? -1));
    });
  }

  async probe(): Promise<EnvStatus> {
    const py = venvPython(this.paths.bioenv);
    if (!existsSync(py)) { this.set({ ready: false, step: 'idle', message: '尚未安装', progress: 0 }); return this.status; }
    const info = await this.pythonInfo(py);
    if (info) this.set({ ready: true, step: 'ready', message: '环境就绪', progress: 1, pythonPath: py, ...info });
    else this.set({ ready: false, step: 'error', message: '环境损坏，请重新安装', progress: 0 });
    return this.status;
  }

  private pythonInfo(py: string): Promise<{ pythonVersion: string; packages: Record<string, string> } | null> {
    return new Promise((resolve) => {
      const code = `import json,sys,importlib.metadata as m
pk={}
for n in ["scanpy","anndata","numpy","pandas","scipy","leidenalg","umap-learn","matplotlib","statsmodels","scikit-learn"]:
  try: pk[n]=m.version(n)
  except Exception: pass
print(json.dumps({"pythonVersion":sys.version.split()[0],"packages":pk}))`;
      const child = spawn(py, ['-c', code], { windowsHide: true });
      let out = '';
      child.stdout.on('data', (b) => (out += b.toString()));
      child.on('error', () => resolve(null));
      child.on('close', (c) => {
        if (c !== 0) return resolve(null);
        try { const j = JSON.parse(out.trim()); resolve(j.packages.scanpy ? j : null); } catch { resolve(null); }
      });
    });
  }

  async install(useChinaMirror: boolean): Promise<EnvStatus> {
    if (this.running) return this.status;
    this.running = true;
    try {
      if (!existsSync(uvBinary())) throw new Error(`找不到 uv：${uvBinary()}`);
      mkdirSync(this.paths.bioenv, { recursive: true });
      for (const f of ['pyproject.toml', 'uv.lock']) {
        cpSync(resourcePath('bioenv', f), path.join(this.paths.bioenv, f));
      }
      const env = this.uvEnv(useChinaMirror);
      this.set({ ready: false, step: 'python', message: '正在下载 Python 3.12…', progress: 0.05, log: [] });
      let code = await this.run(['python', 'install', '3.12'], env, this.paths.bioenv);
      if (code !== 0) throw new Error('Python 下载失败，请检查网络后重试');
      this.set({ step: 'venv', message: '正在创建虚拟环境…', progress: 0.2 });
      code = await this.run(['venv', '--python', '3.12', '--allow-existing', path.join(this.paths.bioenv, '.venv')], env, this.paths.bioenv);
      if (code !== 0) throw new Error('创建虚拟环境失败');
      this.set({ step: 'packages', message: '正在安装分析软件包（scanpy 等，约需几分钟）…', progress: 0.3 });
      let n = 0;
      code = await this.run(['sync', '--frozen', '--python', '3.12'], env, this.paths.bioenv, (l) => {
        if (/^\s*[+~-]\s/.test(l) || /Installed|Prepared|Downloading/.test(l)) {
          n += 1;
          this.set({ progress: Math.min(0.9, 0.3 + n / 150), message: `正在安装分析软件包… ${l.trim().slice(0, 60)}` });
        }
      });
      if (code !== 0) throw new Error('安装软件包失败（通常是网络问题，可重试）');
      this.set({ step: 'verify', message: '正在验证…', progress: 0.95 });
      const info = await this.pythonInfo(venvPython(this.paths.bioenv));
      if (!info) throw new Error('验证失败：scanpy 无法导入');
      this.set({ ready: true, step: 'ready', message: '环境就绪', progress: 1, pythonPath: venvPython(this.paths.bioenv), ...info });
    } catch (e) {
      this.set({ ready: false, step: 'error', message: e instanceof Error ? e.message : String(e), progress: 0 });
    } finally {
      this.running = false;
    }
    return this.status;
  }
}
