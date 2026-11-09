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
    (pkg,) = srv["packages"]
    assert (pkg["registryType"], pkg["identifier"], pkg["version"]) == ("pypi", "krouter", version)
    assert pkg["transport"] == {"type": "stdio"}
    assert [a["value"] for a in pkg["packageArguments"]] == ["mcp"]
    # PyPI 归属校验：README（也是包的长描述）里必须有同名的 mcp-name 标记
    assert f"mcp-name: {srv['name']}" in (ROOT / "README.md").read_text(encoding="utf-8")
