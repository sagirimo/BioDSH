// Extra prompt section for the BioDSH preset, taken from the `appContext` setting (Host row `biodsh`). An embedding
// application (the BioDSH desktop app) uses it to describe its own UI to the agent without restating the preset;
// empty means no section. Placed right after the persona so it stays in the cacheable prefix.
import { setting } from './settings.js';
import { hasSpecification } from './persona.js';
import { workspaceRoot } from './task_policy.js';

// With a written specification in the folder the app description is replaced by a spec-first instruction (the
// short-persona configuration of the benchmark; see persona.js).
export const SPEC_CONTEXT = 'This task comes with written specifications. Open the prompt and every file it names, and every JSON specification in the folder and inputs/, and read each to the end before writing code. Use exactly the identifiers, tokens, units, scopes and definitions they give; when a field is not defined there, say so instead of inventing one. Implement the analysis, run the required self-check, re-read the outputs from disk against the specification, fix what fails, and report what you computed.';

export const name = 'biodsh-context';
export const inject = ['systemPrompt'];

export function apply(ctx) {
  ctx.systemPrompt.section({ name: 'biodsh:app-context', order: 5, interpolate: false, text: (context) => (hasSpecification(workspaceRoot(ctx, context?.agent)) ? SPEC_CONTEXT : String(setting(ctx, 'appContext') || '')) });
}
