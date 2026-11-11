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
    # 登记条目描述的是已发布的那一版：包的版本领先于它时（CHANGELOG 顶部是「未发布」），条目保持指向已发布的资产，
    # 发版时随 tag 一起改（版本、地址、SHA-256）
    if srv["version"] != version:
        # 条目落后时：它指向的那一版必须是 CHANGELOG 里已发布（有日期）的一版，且当前版本（或「未发布」的那一版）在它之后
        log = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert re.search(rf"^## {re.escape(srv['version'])} — \d{{4}}-\d{{2}}-\d{{2}}", log, re.M), "server.json points at a version that was never released"
        assert re.search(rf"^## {re.escape(version)} — ", log, re.M), "the package version has no CHANGELOG section"
        version = srv["version"]
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
