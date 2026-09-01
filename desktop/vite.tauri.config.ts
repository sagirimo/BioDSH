import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'node:path';

// Tauri 版渲染层：同一套 React 代码，只是把 Electron 的 preload 桥换成 Tauri 桥（见 src/renderer/src/tauri-bridge.ts）
export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  base: './',
  define: { 'import.meta.env.BIODSH_TAURI': 'true' },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': resolve(__dirname, 'src/renderer/src'), '@shared': resolve(__dirname, 'src/shared') } },
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  build: { outDir: resolve(__dirname, 'dist-tauri'), emptyOutDir: true, target: ['es2022', 'chrome110', 'safari16'] },
});
