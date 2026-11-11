"""PyPI 长描述：发布前把 README 的相对链接改成绝对地址，mcp-name 标记必须留着。"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pypi_readme", ROOT / "scripts" / "pypi_readme.py")
pypi_readme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pypi_readme)


def test_relative_links_become_absolute_and_the_rest_stays():
    src = (
        '<!-- mcp-name: io.github.x/y -->\n'
        '![demo](docs/img/demo.gif) [install](docs/INSTALL.md#without-an-api-key) [top](#install)\n'
        '[![ci](https://example.com/b.svg)](https://example.com/ci) [lic](./LICENSE "MIT")\n'
        '<img src="docs/img/a.svg"> <source srcset="docs/img/b.svg"> <a href="mailto:x@example.com">m</a>\n'
    )
    out = pypi_readme.rewrite(src, "v9.9.9")
    raw = "https://raw.githubusercontent.com/398894496-arch/KRouter/v9.9.9/"
    blob = "https://github.com/398894496-arch/KRouter/blob/v9.9.9/"
    assert f"![demo]({raw}docs/img/demo.gif)" in out
    assert f"[install]({blob}docs/INSTALL.md#without-an-api-key)" in out
    assert "[top](#install)" in out
    assert "[![ci](https://example.com/b.svg)](https://example.com/ci)" in out
    assert f'[lic]({blob}LICENSE "MIT")' in out
    assert f'src="{raw}docs/img/a.svg"' in out and f'srcset="{raw}docs/img/b.svg"' in out
    assert 'href="mailto:x@example.com"' in out
    assert out.startswith("<!-- mcp-name: io.github.x/y -->")


def test_the_real_readme_has_no_relative_link_left():
    out = pypi_readme.rewrite((ROOT / "README.md").read_text(encoding="utf-8"), "v" + pypi_readme.version())
    left = re.findall(r"\]\((?!https?://|#|mailto:)([^)\s]+)", out) + re.findall(r'(?:src|srcset|href)="(?!https?://|#|mailto:)([^"]+)"', out)
    assert left == []
    assert "mcp-name: io.github.398894496-arch/krouter" in out
