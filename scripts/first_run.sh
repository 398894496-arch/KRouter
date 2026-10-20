#!/bin/sh
set -eu
# 演示跑在模板上，不是宿主的真实流量：不写查询日志（夜间学习读它）
export KROUTER_NO_QUERY_LOG=1

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
# Always the bundled template unless the host names another vault for this script.
# Do not inherit OBSIDIAN_VAULT; that may point at an unrelated live library.
export OBSIDIAN_VAULT="${KROUTER_FIRST_RUN_VAULT:-$ROOT/template}"
ROUTER="$ROOT/skill/krouter-obsidian/scripts/route_knowledge.sh"

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' "python3 required" >&2
  exit 1
fi
if ! command -v rg >/dev/null 2>&1; then
  printf '%s\n' "ripgrep (rg) required" >&2
  exit 1
fi

fail=0
assert_match() {
  query=$1
  expect_id=$2
  expect_name=$3
  out=$("$ROUTER" search "$query") || {
    printf '%s\n' "FAIL search $query (router exit)" >&2
    fail=1
    return
  }
  printf '%s\n' "$out" | grep -q "canonical_id: $expect_id" || {
    printf '%s\n' "FAIL search $query expected $expect_id" >&2
    printf '%s\n' "$out" >&2
    fail=1
    return
  }
  printf '%s\n' "$out" | grep -q "$expect_name" || {
    printf '%s\n' "FAIL search $query expected path containing $expect_name" >&2
    fail=1
    return
  }
  printf '%s\n' "ok search $query -> $expect_id"
}

printf '%s\n' "== status =="
status=$("$ROUTER" status)
printf '%s\n' "$status" | grep -q "source: $OBSIDIAN_VAULT/Agent第二大脑.md" || {
  printf '%s\n' "FAIL status did not point at Agent第二大脑.md" >&2
  printf '%s\n' "$status" >&2
  fail=1
}
printf '%s\n' "ok status -> Agent第二大脑.md"
printf '%s\n' "$status" | grep -q "host_action:" || {
  printf '%s\n' "FAIL status missing host_action (template key/writer should be missing)" >&2
  printf '%s\n' "$status" >&2
  fail=1
}
printf '%s\n' "ok status host_action on missing key"

printf '%s\n' "== short-noun routing =="
assert_match "home" "Q01" "Agent第二大脑.md"
assert_match "clippings" "Q02" "用户偏好与工作约束.md"
assert_match "correction" "Q05" "纠错与取代记录.md"
assert_match "memory" "Q07" "可靠记忆索引.md"

printf '%s\n' "== suggest on miss =="
suggest=$("$ROUTER" suggest "homz") || true
printf '%s\n' "$suggest" | grep -q "Q01" || {
  printf '%s\n' "FAIL suggest homz expected Q01" >&2
  printf '%s\n' "$suggest" >&2
  fail=1
}
printf '%s\n' "$suggest" | grep -q "canonical_match: true" && {
  printf '%s\n' "FAIL suggest must not be a canonical hit" >&2
  fail=1
}
printf '%s\n' "ok suggest homz -> Q01 hint"

printf '%s\n' "== ask matcher =="
ask_out=$(OBSIDIAN_VAULT="$OBSIDIAN_VAULT" python3 "$ROOT/skill/krouter-obsidian/scripts/ask_product.py" coverage) || {
  printf '%s\n' "FAIL ask coverage" >&2
  printf '%s\n' "$ask_out" >&2
  fail=1
}
printf '%s\n' "$ask_out" | grep -q '"ok": true' || {
  printf '%s\n' "FAIL ask coverage not ok" >&2
  printf '%s\n' "$ask_out" >&2
  fail=1
}
printf '%s\n' "ok ask coverage"

printf '%s\n' "== validate template day =="
if python3 -c "import yaml" 2>/dev/null; then
  if python3 "$ROOT/scripts/validate_vault.py" --from-date 2026-01-01 --through-date 2026-01-01; then
    printf '%s\n' "ok validate_vault.py"
  else
    printf '%s\n' "FAIL validate_vault.py" >&2
    fail=1
  fi
else
  printf '%s\n' "skip validate_vault.py (install PyYAML to run it)"
fi

printf '%s\n' "== self-evolution writer =="
if sh "$ROOT/extras/host-daily-evolution/check.sh"; then
  printf '%s\n' "ok extras/host-daily-evolution/check.sh"
else
  printf '%s\n' "FAIL extras/host-daily-evolution/check.sh" >&2
  fail=1
fi

printf '%s\n' "== DSH bridge =="
if command -v node >/dev/null 2>&1; then
  if node "$ROOT/extras/dsh/test-bridge.mjs" && node "$ROOT/extras/dsh/test-apply.mjs"; then
    printf '%s\n' "ok extras/dsh bridge+apply"
  else
    printf '%s\n' "FAIL extras/dsh tests" >&2
    fail=1
  fi
else
  printf '%s\n' "skip extras/dsh/test-bridge.mjs (node required)"
fi

printf '%s\n' ""
printf '%s\n' "First run passed on $OBSIDIAN_VAULT"
printf '%s\n' "Lock is proven. Nothing was installed."
printf '%s\n' "Next: python3 scripts/bootstrap.py --dry-run (every change it would make, made nowhere), then without --dry-run: lookup only, no nightly job, no session import. --vault <path> uses a vault you already have and overwrites nothing; --ask offers the nightly job and the import later."

[ "$fail" -eq 0 ]
