import type { BiodshApi } from '../../preload/index';
declare global { interface Window { biodsh: BiodshApi & { mode?: 'tauri' } } interface ImportMetaEnv { readonly BIODSH_TAURI?: boolean } }
export {};
