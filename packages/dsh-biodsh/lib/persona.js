// BioDSH persona: the same prefix/suffix row as @deepseek-ai/dsh-persona, except that the prefix is chosen per agent.
//
// When the working folder ships a machine-readable output specification (CONTRACT_FILES), the agent gets a one-line
// persona and works from the specification; otherwise it gets the full BioDSH persona from the preset. On the
// 120-task benchmark the short persona was as accurate as the full one (all of those tasks ship a specification);
// open questions and chat were not evaluated with it, so they keep the full persona.
import { existsSync } from 'node:fs';
import path from 'node:path';
import { hostImport } from './host.js';
import { CONTRACT_FILES, workspaceRoot } from './task_policy.js';

const { default: z } = await hostImport('@deepseek-ai/schemastery');

// Section names owned by @deepseek-ai/dsh-system-prompt (PERSONA_PREFIX_SECTION / PERSONA_SUFFIX_SECTION).
const PREFIX_SECTION = 'deployment:persona-prefix';
const SUFFIX_SECTION = 'deployment:persona-suffix';

export const SPEC_PERSONA = 'You are BioDSH, a bioinformatics analysis assistant powered by the {{model}} model.';

export const name = 'biodsh-persona';
export const inject = ['systemPrompt'];
export const Config = z.object({
  prefix: z.string().required(),
  suffix: z.string().default(''),
});

export function hasSpecification(root, hasFile = existsSync) {
  return Boolean(root) && CONTRACT_FILES.some(n => hasFile(path.join(root, n)));
}

export function apply(ctx, config) {
  const prefix = (context) => (hasSpecification(workspaceRoot(ctx, context?.agent)) ? SPEC_PERSONA : config.prefix);
  ctx.effect(() => ctx.systemPrompt.section({
    name: PREFIX_SECTION,
    order: ctx.systemPrompt.getSectionOrder('DEPLOYMENT_PERSONA_PREFIX'),
    text: prefix,
  }), 'biodsh-persona.section()');
  ctx.effect(() => ctx.systemPrompt.section({
    name: SUFFIX_SECTION,
    order: ctx.systemPrompt.getSectionOrder('DEPLOYMENT_PERSONA_SUFFIX'),
    text: config.suffix ?? '',
  }), 'biodsh-persona.suffix()');
}
