#!/bin/sh
# One line for anyone on macOS / Linux:
#   curl -fsSL https://raw.githubusercontent.com/398894496-arch/KRouter/main/scripts/bootstrap.sh | sh
# Options pass through to bootstrap.py, e.g. `| sh -s -- --vault ~/MyVault --lang en`.
# Fetches the latest release (a tag, never main) into ~/.dsh-krouter/<tag>, checks its SHA-256 against the release's
# SHA256SUMS, points ~/.dsh-krouter/current at it, and runs scripts/bootstrap.py from there. Run again to upgrade;
# `| KROUTER_TAG=v1.2.1 sh` stays on one release. From a clone, it uses the clone.
set -eu

REPO="398894496-arch/KRouter"
HOME_DIR="${KROUTER_HOME:-$HOME/.dsh-krouter}"

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' "需要 Python 3 / Python 3 is required."
  case "$(uname -s)" in
    Darwin) printf '%s\n' "macOS: 终端运行 xcode-select --install，或从 https://www.python.org 下载安装，然后重跑这一行。" ;;
    *) printf '%s\n' "Linux: sudo apt install python3（或你的发行版对应命令），然后重跑这一行。" ;;
  esac
  exit 1
fi

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || true)
if [ -n "$HERE" ] && [ -f "$HERE/bootstrap.py" ] && [ -d "$HERE/../skill/krouter-obsidian" ]; then
  exec python3 "$HERE/bootstrap.py" "$@"
fi

TAG=${KROUTER_TAG:-$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')}
DEST="$HOME_DIR/$TAG"
if [ ! -f "$DEST/scripts/bootstrap.py" ]; then
  mkdir -p "$HOME_DIR"
  TMP=$(mktemp -d "${TMPDIR:-/tmp}/krouter-dl.XXXXXX")
  VER=${TAG#v}
  BASE="${KROUTER_RELEASE_BASE:-https://github.com/$REPO/releases/download/$TAG}"
  if curl -fsSL "$BASE/SHA256SUMS" -o "$TMP/SHA256SUMS"; then
    # 这个 release 带校验和：包必须下得到、对得上，否则停，绝不降级去装未校验的源码
    if ! curl -fsSL "$BASE/dsh-krouter-$VER.tgz" -o "$TMP/pkg.tgz"; then
      printf '%s\n' "下载失败，已停止 / could not download dsh-krouter-$VER.tgz; nothing installed."
      rm -rf "$TMP"
      exit 1
    fi
    WANT=$(grep " dsh-krouter-$VER.tgz\$" "$TMP/SHA256SUMS" | cut -d' ' -f1)
    GOT=$( (sha256sum "$TMP/pkg.tgz" 2>/dev/null || shasum -a 256 "$TMP/pkg.tgz") | cut -d' ' -f1)
    if [ -z "$WANT" ] || [ "$WANT" != "$GOT" ]; then
      printf '%s\n' "校验和不符，已停止 / checksum mismatch for dsh-krouter-$VER.tgz; nothing installed."
      rm -rf "$TMP"
      exit 1
    fi
    tar -xzf "$TMP/pkg.tgz" -C "$TMP"
    rm -rf "$DEST"
    mv "$TMP/package" "$DEST"
    printf '%s\n' "sha256 verified: dsh-krouter-$VER.tgz"
  elif [ "${KROUTER_ALLOW_UNVERIFIED:-}" = "1" ]; then
    printf '%s\n' "注意：按 KROUTER_ALLOW_UNVERIFIED=1 安装未校验的源码归档 / installing the unverified source archive (KROUTER_ALLOW_UNVERIFIED=1)."
    curl -fsSL "https://github.com/$REPO/archive/refs/tags/$TAG.tar.gz" -o "$TMP/src.tar.gz"
    tar -xzf "$TMP/src.tar.gz" -C "$TMP"
    rm -rf "$DEST"
    mv "$TMP"/*-* "$DEST"
  else
    printf '%s\n' "$TAG 没有校验文件，已停止；确需安装未校验的版本请设 KROUTER_ALLOW_UNVERIFIED=1 / $TAG has no SHA256SUMS; stopped (set KROUTER_ALLOW_UNVERIFIED=1 to install it unverified)."
    rm -rf "$TMP"
    exit 1
  fi
  rm -rf "$TMP"
fi
ln -sfn "$DEST" "$HOME_DIR/current"
printf '%s\n' "KRouter $TAG → $HOME_DIR/current"
exec python3 "$HOME_DIR/current/scripts/bootstrap.py" "$@"
