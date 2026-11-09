#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
FORCE=0
WITH_HOOKS=0
for arg in "$@"; do
  case "$arg" in
    --force|--upgrade) FORCE=1 ;;
    --with-hooks) WITH_HOOKS=1 ;;
    -h|--help)
      printf '%s\n' "usage: install.sh [--upgrade] [--with-hooks]"
      printf '%s\n' "copies the KRouter Obsidian skill to ~/.agents/skills/krouter-obsidian"
      printf '%s\n' "copies a Cursor always-on rule to ~/.cursor/rules/"
      printf '%s\n' "copies the ask-as-product rule to ~/.cursor/rules/ask-product.mdc"
      printf '%s\n' "installs the nightly timer (KROUTER_NO_TIMER=1 skips it; the one-line install asks instead)"
      printf '%s\n' "KRouter writer: detect a logged-in Claudian-class CLI, or wire *_API_KEY"
      printf '%s\n' "does not replace an existing skill unless --upgrade (--force is the same)"
      printf '%s\n' "never overwrites your alias table: it lives in the vault (90 系统文件/canonical_sources.psv)"
      printf '%s\n' "undo with scripts/uninstall.sh"
      printf '%s\n' "does not enable hooks unless --with-hooks"
      exit 0
      ;;
  esac
done

SKILL_SRC="$ROOT/skill/krouter-obsidian"
SKILL_DST="${KROUTER_SKILL_HOME:-$HOME/.agents/skills/krouter-obsidian}"
RULE_DST="${KROUTER_CURSOR_RULE:-$HOME/.cursor/rules/krouter-obsidian.mdc}"
ASK_RULE_DST="${KROUTER_ASK_RULE:-$HOME/.cursor/rules/ask-product.mdc}"

if [ -e "$SKILL_DST" ] && [ "$FORCE" -ne 1 ]; then
  printf '%s\n' "skill already exists: $SKILL_DST"
  printf '%s\n' "pass --upgrade to replace the code. Your alias table and ledgers are kept."
  exit 1
fi

mkdir -p "$(dirname "$SKILL_DST")" "$(dirname "$RULE_DST")" "$(dirname "$ASK_RULE_DST")"
# 升级只换代码：别名表、台账、锁文件先挪开，装完放回原处（软链原样保留）
KEEP=$(mktemp -d "${TMPDIR:-/tmp}/krouter-keep.XXXXXX")
if [ -d "$SKILL_DST/scripts" ]; then
  for f in "$SKILL_DST"/scripts/canonical_sources.psv "$SKILL_DST"/scripts/canonical_sources.*.json \
           "$SKILL_DST"/scripts/canonical_alias_ledger.jsonl; do
    if [ -e "$f" ] || [ -L "$f" ]; then mv "$f" "$KEEP/"; fi
  done
fi
rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
SAMPLE_MAP="$SKILL_SRC/scripts/canonical_sources.psv"
if [ -e "$KEEP/canonical_sources.psv" ] || [ -L "$KEEP/canonical_sources.psv" ]; then
  rm -f "$SKILL_DST/scripts/canonical_sources.psv"
fi
for f in "$KEEP"/* ; do
  if [ -e "$f" ] || [ -L "$f" ]; then mv "$f" "$SKILL_DST/scripts/"; fi
done
rmdir "$KEEP" 2>/dev/null || true
chmod +x "$SKILL_DST/scripts/route_knowledge.sh" "$SKILL_DST/scripts/route_knowledge.py" \
  "$SKILL_DST/scripts/canonical_lookup.py" "$SKILL_DST/scripts/ask_product.py"
cp "$ROOT/extras/cursor/krouter-obsidian.mdc" "$RULE_DST"
cp "$ROOT/extras/cursor/ask-product.mdc" "$ASK_RULE_DST"

printf '%s\n' "skill: $SKILL_DST"
printf '%s\n' "cursor rule: $RULE_DST"
printf '%s\n' "ask rule: $ASK_RULE_DST"
printf '%s\n' "Codex snippet: $ROOT/extras/codex/AGENTS.snippet.md"
printf '%s\n' "Claude Code snippet: $ROOT/extras/claude-code/CLAUDE.snippet.md"

RUN_SH="$ROOT/extras/host-daily-evolution/run.sh"
chmod +x "$RUN_SH" "$ROOT/extras/host-daily-evolution/check.sh" \
  "$ROOT/extras/host-daily-evolution/resolve.py" "$ROOT/extras/host-daily-evolution/wire_keys.py"
WRITER="${KROUTER_WRITER:-}"
KEYS_ENV="${KROUTER_KEYS_ENV:-$HOME/.dsh-krouter-keys.env}"
if [ -z "$WRITER" ]; then
  WRITER=$(python3 "$ROOT/extras/host-daily-evolution/wire_keys.py" --detect) || WRITER=""
  if [ -n "$WRITER" ]; then
    export KROUTER_WRITER=$WRITER
    printf '%s\n' "detected writer: $WRITER"
  fi
fi
printf '%s\n' "self-evolution writer: $RUN_SH"
printf '%s\n' "keys file: $KEYS_ENV (chmod 600). never written into the vault."
wire=$(python3 "$ROOT/extras/host-daily-evolution/wire_keys.py") || wire="missing path=$KEYS_ENV"
printf '%s\n' "key wire: $wire"
case "$wire" in
  present\ *)
    printf '%s\n' "HOST: live graft probed (CLI login or API key). Marker in $KEYS_ENV."
    key_field=present
    ;;
  dead\ *)
    printf '%s\n' "HOST ACTION: existing key failed probe. Replace the API key in $KEYS_ENV, or re-login the CLI."
    key_field=dead
    ;;
  unknown\ *)
    printf '%s\n' "HOST ACTION: could not probe (network). Re-run install.sh when online."
    key_field=missing
    ;;
  *)
    printf '%s\n' "HOST ACTION: self-evolution key missing. Login grok / official Codex / claude, or put *_API_KEY in $KEYS_ENV or on the vault page."
    key_field=missing
    ;;
esac
printf '%s\n' "mounted agent runs status and must tell the host if host_action is present."
if [ -z "${OBSIDIAN_VAULT:-}" ]; then
  printf '%s\n' "timer not loaded: export OBSIDIAN_VAULT to YOUR vault (copy template/ there first), then re-run install.sh."
  printf '%s\n' "do not point the timer at the clone template."
else
  VAULT=$OBSIDIAN_VAULT
  # 记下库的位置（和一行安装同一个文件）：hook、MCP 服务不继承 OBSIDIAN_VAULT 时靠它找到库；已有就不动
  VAULT_FILE="${KROUTER_VAULT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/krouter/vault}"
  if [ ! -s "$VAULT_FILE" ]; then
    mkdir -p "$(dirname "$VAULT_FILE")" && printf '%s\n' "$VAULT" > "$VAULT_FILE" \
      && printf '%s\n' "vault recorded for hooks and MCP: $VAULT_FILE"
  fi
  # 别名表放进库：库里已有就不动；没有就把旧表（不是样例时）搬进去、原位置留软链；全新安装放一份样例
  VAULT_MAP="$VAULT/90 系统文件/canonical_sources.psv"
  OLD_MAP="$SKILL_DST/scripts/canonical_sources.psv"
  if [ -d "$VAULT/90 系统文件" ] && [ ! -e "$VAULT_MAP" ]; then
    if [ -e "$OLD_MAP" ] && ! cmp -s "$OLD_MAP" "$SAMPLE_MAP"; then
      cp "$OLD_MAP" "$VAULT_MAP"
      if [ -L "$OLD_MAP" ]; then
        # 旧表是软链：真文件在别处（另一个工具可能还在写它），不替别人改，交给宿主
        printf '%s\n' "HOST ACTION: $OLD_MAP links to $(readlink "$OLD_MAP"); that file is no longer read. Point it at the vault table: ln -sf '$VAULT_MAP' '$(readlink "$OLD_MAP")'"
      else
        mv "$OLD_MAP" "$OLD_MAP.moved-to-vault"
        ln -s "$VAULT_MAP" "$OLD_MAP"
      fi
      printf '%s\n' "alias table moved into the vault: $VAULT_MAP"
    else
      cp "$SAMPLE_MAP" "$VAULT_MAP"
      printf '%s\n' "alias table seeded (10 sample nouns; rewrite with yours): $VAULT_MAP"
    fi
  elif [ -e "$VAULT_MAP" ]; then
    printf '%s\n' "alias table: $VAULT_MAP (kept)"
  fi
  HEALTH="$VAULT/90 系统文件/自动化/日更健康.md"
  if [ -f "$HEALTH" ]; then
    python3 "$ROOT/extras/host-daily-evolution/patch_health.py" "$HEALTH" self_evolution_key "$key_field" || true
    if [ -n "$WRITER" ]; then
      python3 "$ROOT/extras/host-daily-evolution/patch_health.py" "$HEALTH" krouter_writer present || true
    else
      python3 "$ROOT/extras/host-daily-evolution/patch_health.py" "$HEALTH" krouter_writer missing || true
    fi
  fi
  if [ "${KROUTER_NO_TIMER:-}" = "1" ]; then
    printf '%s\n' "self-evolution timer: not installed (KROUTER_NO_TIMER=1)"
  else
  case "$(uname -s)" in
    Darwin)
      DST="$HOME/Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist"
      mkdir -p "$HOME/Library/LaunchAgents"
      ROUTER="$ROOT/skill/krouter-obsidian/scripts/route_knowledge.sh"
      TIMER_PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:$HOME/.grok/bin:$HOME/.local/bin"
      sed -e "s|__RUN_SH__|$RUN_SH|g" -e "s|__VAULT__|$VAULT|g" -e "s|__HOME__|$HOME|g" \
        -e "s|__ROUTER__|$ROUTER|g" -e "s|__PATH__|$TIMER_PATH|g" \
        -e "s|__WRITER__|$WRITER|g" -e "s|__KEYS_ENV__|$KEYS_ENV|g" \
        "$ROOT/extras/host-daily-evolution/launchd.example.plist" > "$DST"
      if [ "${KROUTER_SKIP_LAUNCHD:-}" = "1" ]; then
        printf '%s\n' "self-evolution timer plist written (load skipped): $DST"
      else
        uid=$(id -u)
        launchctl bootout "gui/$uid/local.dsh-krouter.daily-evolution" >/dev/null 2>&1 || true
        if launchctl bootstrap "gui/$uid" "$DST" >/dev/null 2>&1 || launchctl load "$DST" >/dev/null 2>&1; then
          printf '%s\n' "self-evolution timer loaded: $DST vault=$VAULT"
        else
          printf '%s\n' "self-evolution timer plist written: $DST"
        fi
      fi
      ;;
    Linux)
      # systemd user timer when there is one, else one marked crontab line (idempotent)
      if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        UNIT_DIR="$HOME/.config/systemd/user"
        mkdir -p "$UNIT_DIR"
        sed -e "s|__RUN_SH__|$RUN_SH|g" -e "s|__VAULT__|$VAULT|g" -e "s|__WRITER__|$WRITER|g" \
          -e "s|__KEYS_ENV__|$KEYS_ENV|g" -e "s|__ROUTER__|$ROOT/skill/krouter-obsidian/scripts/route_knowledge.sh|g" \
          "$ROOT/extras/host-daily-evolution/systemd/dsh-krouter-daily.service" > "$UNIT_DIR/dsh-krouter-daily.service"
        cp "$ROOT/extras/host-daily-evolution/systemd/dsh-krouter-daily.timer" "$UNIT_DIR/dsh-krouter-daily.timer"
        if [ "${KROUTER_SKIP_TIMER:-}" = "1" ]; then
          printf '%s\n' "self-evolution timer units written (enable skipped): $UNIT_DIR"
        else
          systemctl --user daemon-reload && systemctl --user enable --now dsh-krouter-daily.timer >/dev/null 2>&1 \
            && printf '%s\n' "self-evolution timer enabled: systemd user timer dsh-krouter-daily vault=$VAULT" \
            || printf '%s\n' "self-evolution timer units written: $UNIT_DIR (enable failed; run: systemctl --user enable --now dsh-krouter-daily.timer)"
        fi
      elif command -v crontab >/dev/null 2>&1 && [ "${KROUTER_SKIP_TIMER:-}" != "1" ]; then
        LINE="10 9 * * * OBSIDIAN_VAULT='$VAULT' KROUTER_KEYS_ENV='$KEYS_ENV' '$RUN_SH' >>'$HOME/.local/state/krouter/daily.log' 2>&1 # dsh-krouter-daily"
        mkdir -p "$HOME/.local/state/krouter"
        { crontab -l 2>/dev/null | grep -v '# dsh-krouter-daily$' || true; printf '%s\n' "$LINE"; } | crontab -
        printf '%s\n' "self-evolution timer installed: crontab 09:10 vault=$VAULT"
      else
        printf '%s\n' "HOST ACTION: no systemd user session and no crontab; install extras/host-daily-evolution/cron.example by hand."
      fi
      ;;
    *)
      printf '%s\n' "HOST ACTION: no timer on this OS; schedule extras/host-daily-evolution/run.sh daily (Windows: scripts/install_windows_task.ps1)."
      ;;
  esac
  fi
  python3 "$ROOT/extras/host-daily-evolution/resolve.py" --sync-health --offline >/dev/null || true
fi
[ "${KROUTER_BOOTSTRAP:-}" = "1" ] || printf '%s\n' "next: run ./scripts/first_run.sh against the template, then point OBSIDIAN_VAULT at your vault."

if [ "$WITH_HOOKS" -eq 1 ]; then
  HOOK_DST="${KROUTER_HOOK_HOME:-$HOME/.cursor/hooks/krouter-exec-gate.py}"
  mkdir -p "$(dirname "$HOOK_DST")"
  cp "$ROOT/extras/hooks/exec-gate.py" "$HOOK_DST"
  printf '%s\n' "hook script: $HOOK_DST"
  printf '%s\n' "merge extras/hooks/hooks.json.example into ~/.cursor/hooks.json and replace the python3 path with:"
  printf '%s\n' "python3 $HOOK_DST"
  printf '%s\n' "hook process must inherit OBSIDIAN_VAULT. default install does not rewrite hooks.json."
fi
