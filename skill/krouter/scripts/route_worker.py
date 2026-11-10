#!/usr/bin/env python3
"""A resident lookup process for the MCP server: the same `route_knowledge.py` lookups, without starting Python for
each one.

The server keeps a few of these per vault. Each reads one JSON request per line on stdin and writes one JSON reply per
line on stdout:

    {"argv": ["search", "what port does the api use"], "env": {"KROUTER_NO_QUERY_LOG": "1"}, "refresh": false}
    {"code": 0, "out": "route: search\\n…", "err": ""}

`out` and `err` are exactly what `route_knowledge.py <argv>` would print, so the answer is the same as a one-shot
lookup. `env` applies to that request only. Under `KROUTER_REFRESH_EVERY` (the server sets it) a lookup re-checks the
vault's files at most once in that many seconds; `"refresh": true` makes the next one re-check now (after a write).
The vault is the process's `OBSIDIAN_VAULT`, set once when the server starts it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import recall_index  # noqa: E402
import route_knowledge  # noqa: E402


def handle(req: dict) -> dict:
    argv = [str(a) for a in req.get("argv") or []]
    env = {str(k): str(v) for k, v in (req.get("env") or {}).items()}
    if req.get("refresh"):
        recall_index.forget_refresh()
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = [str(HERE / "route_knowledge.py"), *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = route_knowledge.main()
            except SystemExit as exc:  # 路由里直接 exit 的分支：照一次性进程的退出码
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except Exception as exc:  # noqa: BLE001  一次查询失败不拖垮这个进程
        code, err = 1, io.StringIO(f"{type(exc).__name__}: {exc}"[:2000])
    finally:
        sys.argv = saved
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return {"code": int(code or 0), "out": out.getvalue(), "err": err.getvalue()}


def main() -> int:
    proto = sys.stdout  # 只有协议走真正的 stdout；查询本身的输出都收进回复里
    sys.stdout = sys.stderr
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except ValueError:
            reply = {"code": 2, "out": "", "err": "bad request"}
        else:
            reply = handle(req if isinstance(req, dict) else {})
        proto.write(json.dumps(reply, ensure_ascii=False) + "\n")
        proto.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
