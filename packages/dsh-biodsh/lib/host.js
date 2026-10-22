// Resolve a package from the running DeepSeek Harness installation, so the bundle uses the host's own copy (same
// version, same module identity) instead of installing a second one into the profile. process.argv[1] is the dsh entry
// script for `dsh web`, the desktop app and the CLI alike; the bundle's own node_modules is the fallback.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export async function hostImport(name) {
  const bases = [process.argv[1], import.meta.url].filter(Boolean);
  let last;
  for (const base of bases) {
    try { return await import(pathToFileURL(createRequire(base).resolve(name)).href); } catch (e) { last = e; }
  }
  throw last;
}
