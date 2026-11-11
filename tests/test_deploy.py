"""The deployment files (Compose, Kubernetes, systemd) start the same server with flags it has, probe the endpoint it
serves, and keep the vault read-only."""

from __future__ import annotations

import configparser
import re
import shlex
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = (REPO / "skill/krouter/scripts/mcp_server.py").read_text(encoding="utf-8")
FLAGS = set(re.findall(r'add_argument\("(--[a-z-]+)"', SERVER))


def _flags(args: list[str]) -> set[str]:
    return {a for a in args if a.startswith("--")}


def test_server_flags_used_by_every_deployment_exist():
    compose = (REPO / "deploy/docker-compose.yml").read_text(encoding="utf-8")
    kube = (REPO / "deploy/kubernetes/krouter.yaml").read_text(encoding="utf-8")
    unit = (REPO / "deploy/systemd/krouter.service").read_text(encoding="utf-8")
    used = set(re.findall(r'"(--[a-z-]+)"', compose + kube))
    used |= {a for a in shlex.split(unit.split("ExecStart=", 1)[1].split("\nRestart", 1)[0].replace("\\\n", " "))
             if a.startswith("--")}
    assert used and used <= FLAGS, used - FLAGS
    assert "/healthz" in SERVER and "/metrics" in SERVER


def test_systemd_unit_is_hardened_and_reads_the_vault_only():
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string((REPO / "deploy/systemd/krouter.service").read_text(encoding="utf-8"))
    svc = cp["Service"]
    assert svc["User"] == "krouter" and svc["NoNewPrivileges"] == "yes" and svc["ProtectSystem"] == "strict"
    assert "/srv/krouter" in svc["ReadOnlyPaths"] and svc["Restart"] == "on-failure"
    assert "mcp_server.py --http" in svc["ExecStart"] and "--bank-token" in svc["ExecStart"]


def test_kubernetes_manifest_shape():
    yaml = pytest.importorskip("yaml")
    docs = list(yaml.safe_load_all((REPO / "deploy/kubernetes/krouter.yaml").read_text(encoding="utf-8")))
    kinds = {d["kind"]: d for d in docs}
    assert set(kinds) == {"Deployment", "Service"}
    pod = kinds["Deployment"]["spec"]["template"]["spec"]
    server = next(c for c in pod["containers"] if c["name"] == "krouter")
    assert server["readinessProbe"]["httpGet"]["path"] == "/healthz"
    assert all(m.get("readOnly") for m in server["volumeMounts"] if m["mountPath"] == "/vault")
    assert server["securityContext"]["readOnlyRootFilesystem"] is True and pod["securityContext"]["runAsNonRoot"]
    assert _flags(server["args"]) <= FLAGS and "--bank-token" in server["args"]
    banks = [a.split("=", 1)[0] for a in server["args"][1::2] if "=" in a and a.startswith(("team", "ops"))]
    assert set(banks) == {"team", "ops"}
    assert kinds["Service"]["spec"]["selector"] == kinds["Deployment"]["spec"]["selector"]["matchLabels"]
