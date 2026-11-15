#!/usr/bin/env python3
"""Set 45, second addendum (bench/memory_honesty/HELDOUT.md): a host model reached through an API reads the standing
index and the hook's note, one message per call.

    python3 bench/subconscious/both.py prepare set45dev --work DIR [--crowd 240 --crowd-capped]
    DEEPSEEK_API_KEY=... python3 bench/subconscious/api_host.py run --work DIR --host deepseek
    python3 bench/subconscious/both.py score --work DIR --host deepseek
    python3 bench/subconscious/api_host.py why --work DIR --host deepseek      # where the cases not right went

`run` sends, for each item of DIR/batch.json, one request: the system message is both.py's instructions word for word,
one sentence saying the call holds one item, then the session-start context; the user message is the item's message
(with the hook's note above it when the hook brought a page). Temperature 0, each item once. Replies go to
DIR/replies_<host>.jsonl as {id, response, ...}, the file both.py scores. A run that stopped is resumed: items with a
reply are not asked again. The key is read from the environment and written nowhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"  # 只用 flash，写死；返回的 model 里出现 pro 就停
MAX_TOKENS = 600
WORKERS = 4
ONE = "This call holds one item: the user message below. Write only your reply to it (any CALL lines first), nothing else."


class Stop(Exception):
    pass


def messages(batch: dict, item: dict) -> list[dict]:
    system = f"{batch['instructions']}\n\n{ONE}\n\ncontext:\n{batch['context']}"
    return [{"role": "system", "content": system}, {"role": "user", "content": item["message"]}]


def call(msgs: list[dict], key: str) -> dict:
    body = json.dumps({"model": MODEL, "messages": msgs, "temperature": 0, "max_tokens": MAX_TOKENS}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {key}",
                                                          "Content-Type": "application/json", "User-Agent": "bench-client"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")[:300]
        except (ValueError, OSError, AttributeError):
            msg = ""
        raise Stop(json.dumps({"http": e.code, "message": msg}))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise Stop(f"{type(e).__name__}: {str(getattr(e, 'reason', e))[:200]}")
    model = d.get("model", "")
    if "pro" in model.lower():
        raise Stop(json.dumps({"unexpected_model": model}))
    ch = d["choices"][0]
    u = d.get("usage") or {}
    return {"response": ch["message"].get("content") or "", "finish_reason": ch.get("finish_reason"), "model": model,
            "usage": {k: u.get(k) for k in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens")}}


def run(work: Path, host: str) -> int:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    batch = json.loads((work / "batch.json").read_text(encoding="utf-8"))
    out = work / f"replies_{host}.jsonl"
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()} if out.exists() else set()
    todo = [i for i in batch["items"] if i["id"] not in done]
    lock, flag = threading.Lock(), {"stop": None}

    def one(item: dict) -> None:
        if flag["stop"]:
            return
        try:
            rec = call(messages(batch, item), key)
        except Stop as e:
            flag["stop"] = f"{item['id']} {e}"
            return
        with lock:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": item["id"], **rec}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()] if out.exists() else []
    tok = Counter()
    for r in rows:
        for k, v in (r.get("usage") or {}).items():
            tok[k] += v or 0
    print(json.dumps({"items": len(batch["items"]), "replies": len(rows), "models": sorted({r.get("model") for r in rows}),
                      "cut_off": sum(r.get("finish_reason") != "stop" for r in rows), "tokens": dict(tok),
                      "stopped": flag["stop"]}, ensure_ascii=False))
    return 1 if flag["stop"] else 0


def why(work: Path, host: str) -> int:
    """For recall and changed cases that are not right under both.py's rule: did the host not look, look and get no
    page, or come back with another page? Nothing here is a new scoring rule; it reads both.py's own detail file."""
    key = json.loads((work / "key.json").read_text(encoding="utf-8"))
    detail = json.loads((work / f"detail_{host}.json").read_text(encoding="utf-8"))
    c: Counter = Counter()
    rows = []
    for pid, k in key.items():
        d = detail.get(pid)
        if not d:
            continue
        if k["kind"] == "quiet":
            c["quiet_n"] += 1
            c["quiet_fetch"] += bool(d["calls"])
            continue
        c[f"{k['kind']}_n"] += 1
        c[f"{k['kind']}_looked"] += bool(d["calls"])
        if k["expect"] in d["hook"] or k["expect"] in d["host"]:
            continue
        how = "other_page" if d["host"] else ("looked_no_page" if d["calls"] else "did_not_look")
        c[f"{k['kind']}_{how}"] += 1
        rows.append({"case": k["id"], "kind": k["kind"], "lang": k["lang"], "how": how, "expect": k["expect"],
                     "host": d["host"]})
    for kind in ("recall", "changed"):
        print(f"{host} {kind}: {c[f'{kind}_n']} cases, the host made a memory fetch on {c[f'{kind}_looked']}; not right: "
              f"did not look {c[f'{kind}_did_not_look']}, looked and got no page {c[f'{kind}_looked_no_page']}, "
              f"another page {c[f'{kind}_other_page']}")
    print(f"{host} quiet: {c['quiet_n']} cases, a memory fetch on {c['quiet_fetch']}")
    for r in rows:
        print("  " + json.dumps(r, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "why"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--host", default="deepseek")
    a = ap.parse_args()
    return run(Path(a.work), a.host) if a.cmd == "run" else why(Path(a.work), a.host)


if __name__ == "__main__":
    raise SystemExit(main())
