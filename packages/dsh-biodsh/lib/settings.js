// BioDSH settings: one Host row (id `biodsh`) whose Config is the user-facing settings of the bundle.
//
// A patch keyed by an existing entry replaces its `config` literally, so settings of plugins inside an agent preset
// cannot be changed without restating the whole preset. A Host row with a Config becomes a settings namespace
// instead (like agent-default-model): it shows in settings/describe, can be changed with settings.mutate or a
// `biodsh:` section in settings.yaml, and needs no knowledge of the preset. Fields are volatile, so changes apply
// to the next step without restarting dsh. The preset rows read it through ctx.get('biodsh'); without this row they
// use their own defaults.
import { hostImport } from './host.js';

const { Service } = await hostImport('@deepseek-ai/cordis');
const { default: z } = await hostImport('@deepseek-ai/schemastery');

export const DEFAULTS = {
  selectEnabled: true, selectProvider: '', selectModel: '', selectMaxInject: 2,
  guardEnabled: true, guardSoftSteps: 40, guardSoftSeconds: 480, guardHardSteps: 60, guardHardSeconds: 780, guardMaxSteps: 80,
  library: true, librarySearchLimit: 8, officialSkillsDir: '', librarySkillsDir: '', appContext: '', debug: false,
};

export default class BioDSHSettings extends Service {
  static Config = z.object({
    selectEnabled: z.boolean().default(DEFAULTS.selectEnabled).volatile().description('Pick and inject fitting skills for each new message.'),
    selectProvider: z.string().default('').volatile().description('Provider route for skill selection; empty uses the agent\'s route, else the default model.'),
    selectModel: z.string().default('').volatile().description('Model for skill selection; empty follows the same rule.'),
    selectMaxInject: z.natural().default(DEFAULTS.selectMaxInject).volatile().description('High-fit skills injected per message.'),
    guardEnabled: z.boolean().default(DEFAULTS.guardEnabled).volatile(),
    guardSoftSteps: z.natural().default(DEFAULTS.guardSoftSteps).volatile().description('Ask to wrap up after this many steps in one turn.'),
    guardSoftSeconds: z.natural().default(DEFAULTS.guardSoftSeconds).volatile().description('…or after this many seconds.'),
    guardHardSteps: z.natural().default(DEFAULTS.guardHardSteps).volatile().description('Ask for a final answer without tools after this many steps.'),
    guardHardSeconds: z.natural().default(DEFAULTS.guardHardSeconds).volatile().description('…or after this many seconds.'),
    guardMaxSteps: z.natural().default(DEFAULTS.guardMaxSteps).volatile().description('End the turn after this many steps (0: no cap).'),
    library: z.boolean().default(DEFAULTS.library).description('Register the 2000+ skill library and the skill_library tool (restart to apply).'),
    librarySearchLimit: z.natural().default(DEFAULTS.librarySearchLimit).volatile(),
    officialSkillsDir: z.string().default('').description('Directory of BioDSH skills; empty uses the copy inside the bundle (restart to apply).'),
    librarySkillsDir: z.string().default('').description('Directory of the skill library; empty uses the copy inside the bundle (restart to apply).'),
    appContext: z.string().default('').volatile().description('Extra instructions added after the persona, e.g. how an embedding app is used.'),
    debug: z.boolean().default(DEFAULTS.debug).volatile().description('Log BioDSH decisions to stderr.'),
  });

  constructor(ctx, config) {
    super(ctx, 'biodsh');
    this.config = config;
  }

  /** Current value of one setting (volatile fields are references read on every call). */
  get(key) {
    const v = this.config?.[key];
    return v && typeof v === 'object' && typeof v.get === 'function' ? v.get() : (v ?? DEFAULTS[key]);
  }
}

/** Read one setting from the Host row when it is mounted, else from the given fallback config. */
export function setting(ctx, key, fallback) {
  try { const s = ctx.get('biodsh'); if (s && typeof s.get === 'function') return s.get(key); } catch {}
  return fallback?.[key] ?? DEFAULTS[key];
}
