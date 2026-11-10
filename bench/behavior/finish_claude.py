#!/usr/bin/env python3
"""record.json for a Claude Code subagent run: WORKDIR/ID/calls.jsonl (what the helper logged) plus the subagent's last
message, passed in a file.   python3 finish_claude.py SET.json WORKDIR ID MESSAGE_FILE"""
import json
import sys
from pathlib import Path

sc = {s["id"]: s for s in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}[sys.argv[3]]
d = Path(sys.argv[2]) / sys.argv[3]
calls = []
log = d / "calls.jsonl"
if log.exists():
    for line in log.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        calls.append({"tool": c["tool"], "server": "krouter", "arguments": c["arguments"],
                      "status": "failed" if c["error"] else "completed", "result": c["result"]})
msg = Path(sys.argv[4]).read_text(encoding="utf-8")
(d / "record.json").write_text(json.dumps({"id": sc["id"], "group": sc["group"], "rc": 0, "calls": calls, "messages": [msg]},
                                          ensure_ascii=False, indent=1), encoding="utf-8")
print(sc["id"], [c["tool"] for c in calls])
