// Extra prompt section for the BioDSH preset, taken from the `appContext` setting (Host row `biodsh`). An embedding
// application (the BioDSH desktop app) uses it to describe its own UI to the agent without restating the preset;
// empty means no section. Placed right after the persona so it stays in the cacheable prefix.
import { setting } from './settings.js';

export const name = 'biodsh-context';
export const inject = ['systemPrompt'];

export function apply(ctx) {
  ctx.systemPrompt.section({ name: 'biodsh:app-context', order: 5, interpolate: false, text: () => String(setting(ctx, 'appContext') || '') });
}
