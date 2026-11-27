# Sourced, not run: finds a Python 3 that really runs, then hands it the script (`krouter_exec_python script.py args…`).
#
# Why: on Windows, `python3` (and `python`, when Python is not on PATH) is often the Microsoft Store app-execution
# alias under %LOCALAPPDATA%\Microsoft\WindowsApps. It exits 9009 and prints nothing, so every hook and lookup that
# called it failed in silence (#103). Claude Code runs hooks through Git Bash there, so this file is what they reach.
#
# macOS and Linux: `python3` is used as before, with no extra process. Anything else (a WindowsApps alias, `python`
# when there is no `python3`, the `py -3` launcher) is tried once with a one-line check before it is trusted: a real
# Store Python passes, the alias does not.
# Returns 127 when nothing runs, so a caller can fall back or say so.

krouter_py_ok() {
  "$@" -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1
}

krouter_exec_python() {
  case "$(uname -s 2>/dev/null)" in
    MINGW* | MSYS* | CYGWIN*) _kr_win=1 ;;
    *) _kr_win= ;;
  esac
  for _kr_py in python3 python; do
    _kr_at=$(command -v "$_kr_py" 2>/dev/null) || continue
    if [ "$_kr_py" = python3 ] && [ -z "$_kr_win" ]; then
      exec "$_kr_py" "$@"
    fi
    case "$_kr_at" in
      *WindowsApps*) krouter_py_ok "$_kr_py" || continue ;;
      *) [ -n "$_kr_win" ] || krouter_py_ok "$_kr_py" || continue ;;
    esac
    exec "$_kr_py" "$@"
  done
  if command -v py >/dev/null 2>&1 && krouter_py_ok py -3; then
    exec py -3 "$@"
  fi
  return 127
}
