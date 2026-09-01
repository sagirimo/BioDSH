import { app } from 'electron';
import path from 'node:path';
import { mkdirSync } from 'node:fs';
import type { AppPaths } from '../shared/types';

// 用户可见的根目录：~/BioDSH。所有状态都在这里，删掉这个目录 = 彻底重置。
export function appPaths(): AppPaths {
  const root = process.env.BIODSH_HOME || path.join(app.getPath('home'), 'BioDSH');
  const p: AppPaths = {
    root,
    dshHome: path.join(root, 'dsh-home'),
    bioenv: path.join(root, 'bioenv'),
    workspace: path.join(root, 'workspace'),
    skills: path.join(root, 'dsh-home', 'skills'),
    logs: path.join(root, 'logs'),
  };
  for (const d of Object.values(p)) mkdirSync(d, { recursive: true });
  return p;
}

// 打包后资源在 process.resourcesPath；开发时在项目 resources/。
export function resourcePath(...parts: string[]): string {
  const base = app.isPackaged ? process.resourcesPath : path.join(app.getAppPath(), 'resources');
  return path.join(base, ...parts);
}

export function uvBinary(): string {
  const name = process.platform === 'win32' ? 'uv.exe' : 'uv';
  return app.isPackaged
    ? path.join(process.resourcesPath, 'bin', name)
    : path.join(app.getAppPath(), 'resources', 'bin', `${process.platform}-${process.arch}`, name);
}

export function venvPython(bioenv: string): string {
  return process.platform === 'win32'
    ? path.join(bioenv, '.venv', 'Scripts', 'python.exe')
    : path.join(bioenv, '.venv', 'bin', 'python');
}

export function venvBinDir(bioenv: string): string {
  return process.platform === 'win32' ? path.join(bioenv, '.venv', 'Scripts') : path.join(bioenv, '.venv', 'bin');
}

// 打包自带的 Node 运行时（dsh 需要 `node --expose-internals`，Electron 内置 Node 不支持该开关）。
export function nodeBinary(): string {
  const rel = process.platform === 'win32' ? 'node.exe' : path.join('bin', 'node');
  return app.isPackaged
    ? path.join(process.resourcesPath, 'node', rel)
    : path.join(app.getAppPath(), 'resources', 'node', `${process.platform}-${process.arch}`, rel);
}
