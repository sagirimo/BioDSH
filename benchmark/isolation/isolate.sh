#!/bin/bash
# Read isolation for CLI agents (2026-10-27). Codex/Claude sandboxes restrict writes, not reads: on 10-23..26 CLI arms read
# private/expected, reference.py and ANSWER_KEY files from the repo and ~/bench/lean_tasks_ro. This runs the agent in a
# user+mount namespace where task stores, other runs/homes, logs and transcripts are empty tmpfs, then drops back to the
# caller's uid (Claude refuses --dangerously-skip-permissions as root). No root needed.
# Usage: isolate.sh <run_dir> <private_home> <shell_home> -- <command...>
set -euo pipefail
RUN=$1 PHOME=$2 SHOME=$3; shift 3; [ "$1" = -- ] && shift
U=/home/$(id -un) C="${WIN_HOME:?set WIN_HOME to /mnt/c/Users/<you>}"
HIDE=("$C/Documents/Project/BioDSH" "$C/bench-ws" "$C/bench-dsh" "$C/bench-ext-out" "$C/bench-codex-scratch"
      "$U/bench/lean_tasks_ro" "$U/bench/runs" "$U/bench/homes" "$U/bench/science" "$U/bench-ext" "$U/bench-archive"
      "$U/.cache/huggingface" "$U/.claude" "$U/.codex" "$U/codex-logs" "/tmp/claude-$(id -u)")
# Answer-host filter in front of the upstream proxy (filter_proxy.py); the hosts entries below cover direct connections.
FP=$(dirname "$(readlink -f "$0")")/filter_proxy.py
if ! (exec 3<>/dev/tcp/127.0.0.1/7891) 2>/dev/null; then
  nohup python3 "$FP" >> "$U/bench/filter_proxy.log" 2>&1 </dev/null & sleep 1
fi
for v in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY npm_config_proxy npm_config_https_proxy; do export $v=http://127.0.0.1:7891; done
export ISO_RUN=$RUN ISO_PHOME=$PHOME ISO_SHOME=$SHOME ISO_UID=$(id -u) ISO_GID=$(id -g) ISO_HIDE="$(printf '%s\n' "${HIDE[@]}")"
exec unshare -Urm bash -c '
  set -euo pipefail
  S=$(mktemp -d /tmp/iso.XXXXXX); i=0
  for p in "$ISO_RUN" "$ISO_PHOME" "$ISO_SHOME"; do mkdir -p "$S/$i"; mount --bind "$p" "$S/$i"; i=$((i+1)); done
  while IFS= read -r d; do [ -d "$d" ] && mount -t tmpfs -o mode=755 none "$d"; done <<< "$ISO_HIDE"
  # 10-28: hide every Windows drive (Windows .exe interop would bypass the namespace: cmd.exe can read C:\ directly),
  # then re-expose only the read-only BioDSH package/skills copy (no .exe files; the runtime root holds codex.exe/claude.exe).
  RT=/mnt/c/BioDSHBench/runtime/v18-pilot-wsl; mkdir -p "$S/rt"; [ -d "$RT" ] && mount --bind "$RT" "$S/rt"
  for drv in /mnt/c /mnt/d /mnt/wsl /mnt/wslg; do [ -d "$drv" ] && mount -t tmpfs -o mode=755 none "$drv"; done
  if [ -n "$(ls -A "$S/rt" 2>/dev/null)" ]; then mkdir -p "$RT"; mount --bind "$S/rt" "$RT"; mount -o remount,bind,ro "$RT"; fi
  i=0; for p in "$ISO_RUN" "$ISO_PHOME" "$ISO_SHOME"; do mkdir -p "$p"; mount --bind "$S/$i" "$p"; i=$((i+1)); done
  # Public benchmarks (BixBench, BioMed-AQA) publish their answers on Hugging Face; 10-23..26 agents downloaded them.
  { cat /etc/hosts; for h in huggingface.co www.huggingface.co hf.co datasets-server.huggingface.co cdn-lfs.huggingface.co \
      cdn-lfs.hf.co cdn-lfs-us-1.hf.co cas-bridge.xethub.hf.co cas-server.xethub.hf.co transfer.xethub.hf.co hf-mirror.com; do
      echo "0.0.0.0 $h"; echo ":: $h"; done; } > "$S/hosts"; mount --bind "$S/hosts" /etc/hosts
  cd "$ISO_RUN/ws" 2>/dev/null || cd "$ISO_RUN"
  exec unshare -U --map-user="$ISO_UID" --map-group="$ISO_GID" -- "$@"' iso "$@"
