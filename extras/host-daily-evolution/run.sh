#!/bin/sh
# Self-evolution writer + nightly upkeep, run by the nightly job once it is installed (the one-line install asks first).
# Key = vault page *_API_KEY or an already-logged-in local CLI. No extra env file.
set -eu

DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$DIR/../.." && pwd)
RESOLVE="$DIR/resolve.py"
BUNDLED_ROUTER="$ROOT/skill/krouter-obsidian/scripts/route_knowledge.sh"

if [ -n "${KROUTER_VAULT:-}" ]; then OBSIDIAN_VAULT=$KROUTER_VAULT; export OBSIDIAN_VAULT; unset KROUTER_VAULT; fi
if [ -z "${OBSIDIAN_VAULT:-}" ]; then
  printf '%s\n' "KRouter: KROUTER_VAULT (or OBSIDIAN_VAULT) is not set. Timer on; distill skipped." >&2
  exit 0
fi

case "${KROUTER_ROUTER:-}" in
  *obsidian-knowledge-router*) KROUTER_ROUTER="" ;;
esac
export KROUTER_ROUTER="${KROUTER_ROUTER:-$BUNDLED_ROUTER}"

if [ "${1:-}" = "--dry-run" ]; then
  # 什么都不调、不写：写手走哪条通道，夜间各步会发什么、估算多少 token、会写哪些文件
  python3 "$RESOLVE" --status --offline
  SK=$(dirname "$KROUTER_ROUTER")
  [ -f "$SK/nightly.py" ] || SK="$ROOT/skill/krouter-obsidian/scripts"
  [ -f "$SK/nightly.py" ] && python3 "$SK/nightly.py" --vault "$OBSIDIAN_VAULT" --dry-run
  exit 0
fi

rc=0
python3 "$RESOLVE" --exec || rc=$?

# Nightly upkeep after the seal. Runs with the job; KROUTER_NIGHTLY=0 turns it off.
# nightly.py runs the five steps (each independent; none changes the seal's exit code) and writes each
# one's outcome to 90 系统文件/自动化/夜间维护.md and the health page, where `status` reads it.
# Model steps use the writer's lane: *_API_KEY first, then the CLI the writer would pick.
if [ "${KROUTER_NIGHTLY:-1}" != 0 ]; then
  SK=$(dirname "$KROUTER_ROUTER")
  [ -f "$SK/nightly.py" ] || SK="$ROOT/skill/krouter-obsidian/scripts"
  python3 "$SK/nightly.py" --vault "$OBSIDIAN_VAULT" >&2 || printf '%s\n' "KRouter: nightly runner failed (rc=$?)" >&2
fi

exit "$rc"
