"""把 README.md 里的相对链接改成指向 GitHub 上这个版本标签的绝对地址，供 PyPI 长描述用。

PyPI 页面没有仓库里的其他文件：相对路径的图片显示不出来，相对链接点进去是 404。
只在发布流程里对检出的副本运行（`python3 scripts/pypi_readme.py README.md`），不提交改写结果。
图片走 raw.githubusercontent.com，其余链接走 github.com/…/blob/<标签>/；`#锚点`、http(s)、mailto 原样保留。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = "398894496-arch/KRouter"
ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)


def _absolute(path: str, tag: str, image: bool) -> str:
    if re.match(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", path, re.I):
        return path
    path = path[2:] if path.startswith("./") else path.lstrip("/")
    base = f"https://raw.githubusercontent.com/{REPO}/{tag}/" if image else f"https://github.com/{REPO}/blob/{tag}/"
    return base + path


def rewrite(text: str, tag: str) -> str:
    # Markdown 链接和图片：[文字](路径) / ![替代文字](路径)，路径后可带 "标题"
    def md(m: re.Match) -> str:
        return f"{m.group(1)}({_absolute(m.group(2), tag, m.group(1).startswith('!'))}{m.group(3) or ''})"

    text = re.sub(r"(!?\[(?:[^\[\]]|\[[^\[\]]*\])*\])\(([^()\s]+)(\s+\"[^\"]*\")?\)", md, text)
    # HTML：src="…"、srcset="…"、href="…"
    text = re.sub(r'\b(src|srcset)="([^"]+)"', lambda m: f'{m.group(1)}="{_absolute(m.group(2), tag, True)}"', text)
    text = re.sub(r'\bhref="([^"]+)"', lambda m: f'href="{_absolute(m.group(1), tag, False)}"', text)
    return text


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else ROOT / "README.md"
    tag = "v" + version()
    before = target.read_text(encoding="utf-8")
    after = rewrite(before, tag)
    if "mcp-name: " not in after:
        sys.exit("README has no mcp-name marker; the MCP registry could not verify the PyPI package")
    target.write_text(after, encoding="utf-8")
    print(f"{target}: relative links now point at {REPO}@{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
