#!/bin/sh
# The release assets, exactly as .github/workflows/release.yml attaches them, built into OUT (default: dist-release/):
#   dsh-krouter-<version>.tgz, bootstrap.sh, bootstrap.ps1, KRouter.mcpb (the Claude Desktop extension), SHA256SUMS
# Then checks them: every release asset README.md / README.zh.md / docs link to is here, SHA256SUMS covers them, and
# the package holds what a release install runs (the router, the installer, the plugin, `krouter` from sdk/, both
# templates, the English layout). Run it locally before tagging; the workflow runs the same script.
#   sh scripts/release_pack.sh [OUT]
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
OUT=${1:-$ROOT/dist-release}
mkdir -p "$OUT"
OUT=$(CDPATH= cd -- "$OUT" && pwd)
cd "$ROOT"
VER=$(python3 -c 'import json; print(json.load(open("package.json"))["version"])')
rm -f "$OUT/dsh-krouter-$VER.tgz" "$OUT/SHA256SUMS"
npm pack --silent --pack-destination "$OUT" >/dev/null
cp scripts/bootstrap.sh scripts/bootstrap.ps1 "$OUT/"   # 一行安装从 releases/latest/download/ 取这两个，不取 main 上的
python3 scripts/build_mcpb.py --out "$OUT/KRouter.mcpb" >/dev/null   # Claude Desktop 的一键扩展包
cd "$OUT"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "dsh-krouter-$VER.tgz" bootstrap.sh bootstrap.ps1 KRouter.mcpb > SHA256SUMS
else
  shasum -a 256 "dsh-krouter-$VER.tgz" bootstrap.sh bootstrap.ps1 KRouter.mcpb > SHA256SUMS
fi
cat SHA256SUMS

fail=0
# 文档里引用的每个发布附件都要在这里
for doc in "$ROOT/README.md" "$ROOT/README.zh.md" "$ROOT"/docs/*.md; do
  for asset in $(grep -o 'releases/latest/download/[A-Za-z0-9._-]*' "$doc" | sed 's#.*/##' | sort -u); do
    if [ ! -f "$OUT/$asset" ]; then
      printf '%s\n' "FAIL $(basename "$doc") links releases/latest/download/$asset, which the release does not attach" >&2
      fail=1
    fi
  done
done
# 发布包里要有一行安装真正会跑的东西
LIST=$(python3 -c 'import sys, tarfile; print("\n".join(tarfile.open(sys.argv[1]).getnames()))' "dsh-krouter-$VER.tgz")  # bsdtar 会转义中文名
for need in package/scripts/bootstrap.py package/scripts/install.sh package/scripts/uninstall.sh package/scripts/krouter \
            package/skill/krouter/scripts/route_knowledge.sh package/skill/krouter/scripts/mcp_server.py \
            package/skill/krouter/scripts/zones_en.psv package/sdk/krouter/cli.py package/sdk/krouter/doctor.py \
            package/skill/krouter/scripts/associate.py package/skill/krouter/scripts/cocite.py \
            package/skill/krouter/scripts/experience.py package/skill/krouter/scripts/llm.py \
            package/skill/krouter/scripts/skills.py \
            package/skill/krouter/scripts/corrections.py package/skill/krouter/scripts/capture_ledger.py \
            package/skill/krouter/scripts/recollect.py package/skill/krouter/scripts/compile_subconscious.py \
            package/skill/krouter/scripts/learn_mentions.py package/skill/krouter/scripts/session_hook.py \
            package/sdk/krouter/integrations/langgraph.py \
            package/sdk/krouter/why.py package/sdk/krouter/view.py package/sdk/krouter/viewdata.py package/sdk/krouter/sample.py \
            package/sdk/krouter/view_ui/index.html package/sdk/krouter/view_ui/app.js package/sdk/krouter/view_ui/app.css \
            package/.claude-plugin/marketplace.json package/.claude-plugin/plugin.json package/hooks/hooks.json \
            package/scripts/build_mcpb.py package/extras/claude-desktop/manifest.json \
            package/template/Agent第二大脑.md package/template-zh/Agent第二大脑.md; do
  printf '%s\n' "$LIST" | grep -qx "$need" || { printf '%s\n' "FAIL the package has no $need" >&2; fail=1; }
done
# 扩展包：照 MCPB 清单规范查结构，再解开真启动一次、走一遍 MCP 握手和查询
python3 "$ROOT/scripts/build_mcpb.py" --check "$OUT/KRouter.mcpb" || fail=1
[ "$fail" -eq 0 ] || exit 1
printf '%s\n' "release assets OK in $OUT (version $VER)"
