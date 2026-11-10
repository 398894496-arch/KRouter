#!/bin/sh
# 卸载 KRouter：停掉并删除定时任务、Cursor 规则、skill 目录、MCP 登记、Claude Code 插件和本机目录的插件市场。不动库。
# 别名表若还只在 skill 目录里（没进库），先复制进库再删，绝不丢。
# --purge 另外删除可重建的缓存和查询日志；钥匙文件永远只提示、不删。
set -eu

PURGE=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help)
      printf '%s\n' "usage: uninstall.sh [--dry-run] [--purge]"
      printf '%s\n' "removes the timer (launchd / systemd user / crontab line), Cursor rules, the hook script, the skill, the MCP registrations,"
      printf '%s\n' "KRouter's Codex / Cursor hooks, the Claude Code plugin (and its marketplace when it points at a folder here) and the recorded vault path"
      printf '%s\n' "never touches the vault, except to save an alias table that is not in it yet"
      printf '%s\n' "--purge also removes the rebuildable cache, the state and query log, and the downloaded release (~/.dsh-krouter);"
      printf '%s\n' "the keys file is never removed"
      exit 0
      ;;
  esac
done

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
SKILL_DST="${KROUTER_SKILL_HOME:-$HOME/.agents/skills/krouter-obsidian}"
RULE_DST="${KROUTER_CURSOR_RULE:-$HOME/.cursor/rules/krouter-obsidian.mdc}"
ASK_RULE_DST="${KROUTER_ASK_RULE:-$HOME/.cursor/rules/ask-product.mdc}"
HOOK_DST="${KROUTER_HOOK_HOME:-$HOME/.cursor/hooks/krouter-exec-gate.py}"
KEYS_ENV="${KROUTER_KEYS_ENV:-$HOME/.dsh-krouter-keys.env}"
SAMPLE_MAP="$ROOT/skill/krouter-obsidian/scripts/canonical_sources.psv"

VAULT_FILE="${KROUTER_VAULT_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/krouter/vault}"
# 没设 OBSIDIAN_VAULT：用一键安装记下的库（下面要往里存别名表、最后要说库在哪）
if [ -z "${OBSIDIAN_VAULT:-}" ] && [ -f "$VAULT_FILE" ]; then
  OBSIDIAN_VAULT=$(head -n 1 "$VAULT_FILE")
fi

run() {
  if [ "$DRY" -eq 1 ]; then printf '%s\n' "would: $*"; else "$@"; fi
}

# 1. timer
case "$(uname -s)" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist"
    if [ -f "$PLIST" ]; then
      [ "$DRY" -eq 1 ] || launchctl bootout "gui/$(id -u)/local.dsh-krouter.daily-evolution" >/dev/null 2>&1 || true
      run rm -f "$PLIST"
      printf '%s\n' "timer removed: $PLIST"
    fi
    ;;
  Linux)
    UNIT_DIR="$HOME/.config/systemd/user"
    if [ -f "$UNIT_DIR/dsh-krouter-daily.timer" ]; then
      [ "$DRY" -eq 1 ] || systemctl --user disable --now dsh-krouter-daily.timer >/dev/null 2>&1 || true
      run rm -f "$UNIT_DIR/dsh-krouter-daily.timer" "$UNIT_DIR/dsh-krouter-daily.service"
      [ "$DRY" -eq 1 ] || systemctl --user daemon-reload >/dev/null 2>&1 || true
      printf '%s\n' "timer removed: systemd user timer dsh-krouter-daily"
    fi
    ;;
esac
if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -q '# dsh-krouter-daily$'; then
  if [ "$DRY" -eq 1 ]; then
    printf '%s\n' "would: remove the '# dsh-krouter-daily' crontab line"
  else
    crontab -l 2>/dev/null | grep -v '# dsh-krouter-daily$' | crontab -
  fi
  printf '%s\n' "timer removed: crontab line"
fi

# 2. alias table: save it into the vault if that is the only copy
MAP="$SKILL_DST/scripts/canonical_sources.psv"
if [ -f "$MAP" ] && [ ! -L "$MAP" ] && ! cmp -s "$MAP" "$SAMPLE_MAP"; then
  VAULT_MAP=""
  [ -z "${OBSIDIAN_VAULT:-}" ] || VAULT_MAP=$(python3 "$ROOT/skill/krouter-obsidian/scripts/zones.py" real "$OBSIDIAN_VAULT" "90 系统文件/canonical_sources.psv")
  if [ -n "$VAULT_MAP" ] && [ -d "$(dirname "$VAULT_MAP")" ] && [ ! -e "$VAULT_MAP" ]; then
    run cp "$MAP" "$VAULT_MAP"
    printf '%s\n' "alias table saved into the vault: $VAULT_MAP"
  else
    SAVE="$HOME/dsh-krouter-canonical_sources.$(date +%Y%m%d%H%M%S).psv"
    run cp "$MAP" "$SAVE"
    printf '%s\n' "alias table saved: $SAVE"
  fi
fi

# 3. rules, hook, skill
for f in "$RULE_DST" "$ASK_RULE_DST" "$HOOK_DST"; do
  if [ -e "$f" ]; then run rm -f "$f"; printf '%s\n' "removed: $f"; fi
done
[ -e "$HOOK_DST" ] || [ ! -f "$HOME/.cursor/hooks.json" ] || ! grep -q krouter-exec-gate "$HOME/.cursor/hooks.json" \
  || printf '%s\n' "HOST ACTION: remove the krouter-exec-gate entry from ~/.cursor/hooks.json"
if [ -e "$SKILL_DST" ] || [ -L "$SKILL_DST" ]; then
  run rm -rf "$SKILL_DST"
  printf '%s\n' "removed: $SKILL_DST"
fi

# 3b. MCP registrations and the recorded vault path (only ours: the server must be KRouter's mcp_server.py)
if [ "${KROUTER_NO_MCP:-0}" != 1 ]; then
  if command -v claude >/dev/null 2>&1 && claude mcp get krouter 2>/dev/null | grep -q 'mcp_server.py'; then
    run claude mcp remove --scope user krouter >/dev/null 2>&1 || true
    printf '%s\n' "removed: MCP server krouter (claude)"
  fi
  if command -v codex >/dev/null 2>&1 && codex mcp get krouter 2>/dev/null | grep -q 'mcp_server.py'; then
    run codex mcp remove krouter >/dev/null 2>&1 || true
    printf '%s\n' "removed: MCP server krouter (codex)"
  fi
  # The Claude Code plugin (its session hooks would keep firing) and the marketplace the installer added from a folder
  # on this machine; desktop apps and editors the installer wired (Claude Desktop, Cursor, VS Code, Copilot CLI,
  # Gemini CLI, Kiro, Zed, Cline): drop only our krouter entry (the one pointing at mcp_server.py), keep the rest
  if [ "$DRY" -eq 1 ]; then
    python3 "$ROOT/scripts/bootstrap.py" --unregister-mcp --dry-run || true
  else
    python3 "$ROOT/scripts/bootstrap.py" --unregister-mcp || true
  fi
fi
if [ -f "$VAULT_FILE" ]; then run rm -f "$VAULT_FILE"; printf '%s\n' "removed: $VAULT_FILE"; fi

# 4. rebuildable state
CACHE="${KROUTER_CACHE_DIR:-$HOME/.cache/krouter}"
STATE="${KROUTER_STATE_DIR:-$HOME/.local/state/krouter}"
RELEASES="${KROUTER_HOME:-$HOME/.dsh-krouter}"
if [ "$PURGE" -eq 1 ]; then
  for d in "$CACHE" "$STATE"; do
    if [ -e "$d" ]; then run rm -rf "$d"; printf '%s\n' "removed: $d"; fi
  done
else
  for d in "$CACHE" "$STATE"; do
    [ -e "$d" ] && printf '%s\n' "kept (rebuildable; --purge removes): $d"
  done
fi
[ -e "$KEYS_ENV" ] && printf '%s\n' "kept: $KEYS_ENV (your keys; delete it yourself if you no longer need it)"
printf '%s\n' "vault untouched: ${OBSIDIAN_VAULT:-<OBSIDIAN_VAULT not set>} (your notes; delete the folder yourself if you want it gone). Codex / Claude snippets you pasted stay where you pasted them."
printf '%s\n' "each app settings file KRouter changed keeps a copy next to it (*.krouter-bak); delete those when you like."
# 下载下来的发布包（一行安装放在 ~/.dsh-krouter/<tag>）：--purge 时最后删（脚本自己可能就在里面，所以放在最后一行）
if [ -d "$RELEASES" ]; then
  if [ "$PURGE" -eq 1 ]; then
    if [ "$DRY" -eq 1 ]; then printf '%s\n' "would: rm -rf $RELEASES"; exit 0; fi
    printf '%s\n' "removed: $RELEASES (downloaded releases)"; rm -rf "$RELEASES"; exit 0
  fi
  printf '%s\n' "kept (downloaded releases; --purge removes): $RELEASES"
fi
exit 0
