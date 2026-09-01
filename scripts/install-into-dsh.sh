#!/usr/bin/env bash
# Install BioDSH's official skills into a DeepSeek Harness (dsh) skills directory.
#
# BioDSH skills are plain dsh-native SKILL.md skills, so vanilla dsh picks them up
# automatically once they sit in a skills folder it scans:
#   • <your dsh project>/.agents/skills/   (default here — per-project, always works)
#   • ~/.agents/skills/                    (global, with --global)
#
# Usage:
#   ./scripts/install-into-dsh.sh                 # into ./.agents/skills of the current dir
#   ./scripts/install-into-dsh.sh --global        # into ~/.agents/skills
#   ./scripts/install-into-dsh.sh /path/to/skills # into a directory you choose
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)/biodsh-core/skills"
case "${1:-}" in
  --global) DEST="$HOME/.agents/skills" ;;
  "")       DEST="$PWD/.agents/skills" ;;
  *)        DEST="$1" ;;
esac
mkdir -p "$DEST"
n=0
for d in "$SRC"/*/; do
  [ -f "$d/SKILL.md" ] || continue
  name="$(basename "$d")"
  rm -rf "$DEST/$name"
  cp -r "$d" "$DEST/$name"
  echo "  installed: $name"
  n=$((n+1))
done
echo "Installed $n BioDSH skill(s) into: $DEST"
echo "Start dsh from a workspace that sees this folder and the skills are ready to use."
echo "Note: the scRNA / plotting skills expect a Python env with scanpy, anndata, pandas, matplotlib on PATH."
