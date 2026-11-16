#!/bin/bash
# Read isolation v3 (2026-11-02). Fixes three gaps found in the 11-01/02 runs (isolate.sh / isolate_bix.sh):
#  1. the home directory was hidden by a deny-list, so unlisted paths stayed readable (~/repack held an unpacked npm
#     package with A-grade contaminated community skills; also dsh-biodsh *.tgz, ~/.npm cache, ~/projects, ~/data);
#     v3 hides ALL of $HOME and re-exposes only an allow-list (ISO_KEEP plus the run dir and the two homes);
#  2. no PID namespace: agents could run `ps aux` / `ls /proc/*/cwd` and read other agents' and the operator's command lines;
#     v3 runs the agent as PID 1 of a new PID namespace with its own /proc;
#  3. background processes started by an agent outlived the task and throttled the next one in the same cgroup;
#     in a PID namespace every process is killed when PID 1 (the agent) exits.
# Kept from v2: Windows drives hidden (interop bypass), read-only runtime bind, Hugging Face hosts blocked, private /tmp and
# /var/tmp per stage, proxy env pointing at the filter/allow proxy.
# Usage: isolate_v3.sh <run_dir> <private_home> <shell_home> -- <command...>
#   ISO_KEEP  extra absolute paths to re-expose read-only (newline separated); default: the benchmark runtimes and env.
#   ISO_KEEP_RW  extra paths re-exposed read-write (e.g. a shared tool cache); default empty.
#   ISO_RT  runtime directory on C: to expose read-only (default v18-pilot-wsl).  ISO_PROXY_PORT (default 7892).
set -euo pipefail
RUN=$1 PHOME=$2 SHOME=$3; shift 3; [ "$1" = -- ] && shift
U=/home/$(id -un)
: "${ISO_RT:=/mnt/c/BioDSHBench/runtime/v18-pilot-wsl}" "${ISO_PROXY_PORT:=7892}"
: "${ISO_KEEP:=$(printf '%s\n' "$U/bench/env" "$U/bench/runtime" "$U/bench/codex-runtime-0.166.0" "$U/bench/claude-runtime-2.1.305" "$U/miniconda3")}"
: "${ISO_KEEP_RW:=}"
for v in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY npm_config_proxy npm_config_https_proxy; do export $v=http://127.0.0.1:$ISO_PROXY_PORT; done
export ISO_RUN=$RUN ISO_PHOME=$PHOME ISO_SHOME=$SHOME ISO_UID=$(id -u) ISO_GID=$(id -g) ISO_U=$U ISO_RT ISO_KEEP ISO_KEEP_RW
exec unshare -Urm --pid --fork bash -c '
  set -euo pipefail
  S=$(mktemp -d /tmp/iso.XXXXXX)
  # stage every path that must stay visible, then blank $HOME, /tmp-of-host, Windows drives, and bind them back
  stage() { local i=0 p; while IFS= read -r p; do [ -n "$p" ] && [ -e "$p" ] || continue; mkdir -p "$S/$1/$i"; mount --rbind "$p" "$S/$1/$i"; echo "$p" >> "$S/$1.list"; i=$((i+1)); done; }
  printf "%s\n" "$ISO_RUN" "$ISO_PHOME" "$ISO_SHOME" | stage rw
  printf "%s\n" "$ISO_KEEP_RW" | stage rw2
  printf "%s\n" "$ISO_KEEP" | stage ro
  mkdir -p "$S/rt"; [ -d "$ISO_RT" ] && mount --bind "$ISO_RT" "$S/rt"
  mount -t tmpfs -o mode=755 none "$ISO_U"
  for drv in /mnt/c /mnt/d /mnt/wsl /mnt/wslg; do [ -d "$drv" ] && mount -t tmpfs -o mode=755 none "$drv"; done
  restore() { local i=0 p; [ -f "$S/$1.list" ] || return 0; while IFS= read -r p; do mkdir -p "$p"; mount --rbind "$S/$1/$i" "$p"; [ "$2" = ro ] && mount -o remount,bind,ro "$p"; i=$((i+1)); done < "$S/$1.list"; }
  restore rw rw; restore rw2 rw; restore ro ro
  if [ -n "$(ls -A "$S/rt" 2>/dev/null)" ]; then mkdir -p "$ISO_RT"; mount --bind "$S/rt" "$ISO_RT"; mount -o remount,bind,ro "$ISO_RT"; fi
  { cat /etc/hosts; for h in huggingface.co www.huggingface.co hf.co datasets-server.huggingface.co cdn-lfs.huggingface.co \
      cdn-lfs.hf.co cdn-lfs-us-1.hf.co cas-bridge.xethub.hf.co cas-server.xethub.hf.co transfer.xethub.hf.co hf-mirror.com; do
      echo "0.0.0.0 $h"; echo ":: $h"; done; } > "$S/hosts"; mount --bind "$S/hosts" /etc/hosts
  mkdir -p "$ISO_RUN/tmp" "$ISO_RUN/vartmp"; mount --bind "$ISO_RUN/tmp" /tmp; mount --bind "$ISO_RUN/vartmp" /var/tmp
  mount -t proc proc /proc
  cd "$ISO_RUN/ws" 2>/dev/null || cd "$ISO_RUN"
  exec unshare -U --map-user="$ISO_UID" --map-group="$ISO_GID" -- "$@"' iso "$@"
