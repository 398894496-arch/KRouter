#!/bin/sh
# awk 在 UTF-8 区域设置下按排序规则比较字符串（BSD/macOS awk 用 strcoll），汉字可能被当成"相等"，
# 路径换算就会选错一行（CI 上 en_US.UTF-8 时 日更健康 → Memory changes）。按字节比较：
awk() { LC_ALL=C command awk "$@"; }
# Prove the self-evolution writer is present and the vault lamp is readable.
# lamp is running (nightly job installed) or unused (not installed). Does not fire the daily job.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
VAULT="${KROUTER_VAULT:-${OBSIDIAN_VAULT:-$ROOT/template}}"
ZONES="$ROOT/skill/krouter/scripts/zones.py"
HEALTH=$(python3 "$ZONES" real "$VAULT" "90 系统文件/自动化/日更健康.md")

if [ ! -f "$HEALTH" ]; then
  printf '%s\n' "FAIL missing health page: $HEALTH" >&2
  exit 1
fi

lamp=$(awk '
  BEGIN { in_fm=0 }
  /^---$/ { in_fm++; if (in_fm==2) exit }
  in_fm==1 && $1=="lamp:" { print $2; exit }
' "$HEALTH")
lamp=${lamp:-unset}

case "$lamp" in
  running)
    printf '%s\n' "ok self-evolution lamp=running (timer on) on $HEALTH"
    ;;
  unused)
    printf '%s\n' "ok self-evolution lamp=unused (no nightly job installed) on $HEALTH"
    ;;
  *)
    printf '%s\n' "FAIL lamp must be running (default) or unused (got: $lamp) in $HEALTH" >&2
    printf '%s\n' "timer on: lamp: running. you turned it off: lamp: unused." >&2
    exit 1
    ;;
esac

for f in README.md PROMPT.md check.sh run.sh resolve.py api_writer.py wire_keys.py patch_health.py launchd.example.plist cron.example; do
  p="$ROOT/extras/host-daily-evolution/$f"
  if [ ! -f "$p" ]; then
    printf '%s\n' "FAIL missing writer file: $p" >&2
    exit 1
  fi
done

KEY_PAGE=$(python3 "$ZONES" real "$VAULT" "90 系统文件/自动化/自进化钥匙.md")
if [ ! -f "$KEY_PAGE" ]; then
  printf '%s\n' "FAIL missing key page: $KEY_PAGE" >&2
  exit 1
fi
if grep -E '^(export[[:space:]]+)?[A-Z][A-Z0-9_]+=(sk-|AIza|xai-)' "$KEY_PAGE" >/dev/null 2>&1; then
  printf '%s\n' "FAIL key page must ship placeholders only, not a live key" >&2
  exit 1
fi
printf '%s\n' "ok self-evolution key page present (placeholders only)"

printf '%s\n' "ok self-evolution writer files present (this check does not fire the job)"
