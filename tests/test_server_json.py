"""server.json (the MCP registry entry) stays in step with the package it points at."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_server_json_matches_the_package_and_the_readme_marker():
    srv = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", srv["name"])
    assert 1 <= len(srv["description"]) <= 100
    assert srv["version"] == version
    assert srv["packages"]
    for pkg in srv["packages"]:
        assert pkg["transport"] == {"type": "stdio"}
        if pkg["registryType"] == "pypi":
            assert (pkg["identifier"], pkg["version"]) == ("krouter", version)
            assert [a["value"] for a in pkg["packageArguments"]] == ["mcp"]
        else:
            # 扩展包：v<版本> 发布页上的 KRouter.mcpb（release.yml 附上的那个），带它的 SHA-256；地址里要有 "mcp"（registry 的归属规则）
            assert pkg["registryType"] == "mcpb"
            assert pkg["identifier"] == f"https://github.com/398894496-arch/KRouter/releases/download/v{version}/KRouter.mcpb"
            assert re.fullmatch(r"[0-9a-f]{64}", pkg["fileSha256"])
    # PyPI 归属校验：README（也是包的长描述）里必须有同名的 mcp-name 标记（包条目换回 PyPI 时要用）
    assert f"mcp-name: {srv['name']}" in (ROOT / "README.md").read_text(encoding="utf-8")
