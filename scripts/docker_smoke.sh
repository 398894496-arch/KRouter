#!/bin/sh
# 团队服务器镜像的冒烟测试：只读挂一个示例库，等健康检查变绿，不带 token 必须 401，带 token 的查询要带库名回来，
# 访问日志只有问题的 hash，库里一个文件都不能变。CI 和发版流程都跑它；本机有 Docker 也能跑。
#   sh scripts/docker_smoke.sh krouter:test
set -eu
IMAGE=${1:?usage: docker_smoke.sh IMAGE}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
# 绑定挂载的目录要在 Docker 看得见的地方：colima / Docker Desktop 只共享用户目录时设 KROUTER_SMOKE_TMP=$HOME/...
WORK=$(mktemp -d "${KROUTER_SMOKE_TMP:-${TMPDIR:-/tmp}}/krouter-smoke.XXXXXX")
NAME=krouter-smoke-$$
PORT=${KROUTER_SMOKE_PORT:-18787}
TOKEN=smoke-test-token-0123456789
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT
cp -R "$ROOT/template" "$WORK/vault"
printf '%s\n' "$TOKEN" > "$WORK/token"
chmod 644 "$WORK/token"   # 容器里的非 root 用户要能读
sums() { (cd "$WORK/vault" && find . -type f -exec cksum {} \; | sort); }
sums > "$WORK/before"
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8787" \
  -v "$WORK/vault:/vault:ro" -v "$WORK/token:/run/secrets/krouter_token:ro" "$IMAGE" >/dev/null
state=starting
i=0
while [ $i -lt 60 ]; do
  state=$(docker inspect -f '{{.State.Health.Status}}' "$NAME")
  [ "$state" = healthy ] || [ "$state" = unhealthy ] && break
  sleep 2
  i=$((i + 1))
done
[ "$state" = healthy ] || { docker logs "$NAME"; echo "smoke: container is $state"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}' "http://127.0.0.1:$PORT/mcp")
[ "$code" = 401 ] || { echo "smoke: no token gave $code, want 401"; exit 1; }
curl -s -X POST -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"krouter_ask","arguments":{"query":"smoke-test question 发版流程怎么定的"}}}' \
  "http://127.0.0.1:$PORT/mcp" > "$WORK/reply.json"
python3 - "$WORK/reply.json" <<'PY'
import json, sys
reply = json.load(open(sys.argv[1], encoding="utf-8"))["result"]
text = reply["content"][0]["text"]
assert not reply["isError"], text
assert text.startswith("vault_label: team\n") and "receipt_version:" in text, text[:300]
PY
docker logs "$NAME" 2>&1 | grep -q '"q_sha256"' || { echo "smoke: no hashed question in the access log"; exit 1; }
if docker logs "$NAME" 2>&1 | grep -q 'smoke-test question'; then echo "smoke: the question text reached the log"; exit 1; fi
sums > "$WORK/after"
cmp -s "$WORK/before" "$WORK/after" || { echo "smoke: the vault changed"; exit 1; }
[ "$(docker exec "$NAME" id -u)" != 0 ] || { echo "smoke: runs as root"; exit 1; }
echo "smoke ok: $IMAGE healthy, token enforced, receipt labelled, question hashed, vault untouched, not root"
