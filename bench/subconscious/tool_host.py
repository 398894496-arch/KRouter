#!/usr/bin/env python3
"""Set 47 (bench/memory_honesty/HELDOUT.md): the same messages, three things in the host's hands, tools run for real.

    python3 bench/subconscious/tool_host.py prepare --work DIR [--crowd 1000 [--mixed]]
    DEEPSEEK_API_KEY=... python3 bench/subconscious/tool_host.py run --work DIR --cond folder|listed|krouter|k1|k2|k3|k4
    python3 bench/subconscious/tool_host.py score --work DIR --cond ...
    DEEPSEEK_API_KEY=... python3 bench/subconscious/tool_host.py judge --work DIR --cond ...     # does the reply carry the rule?

Conditions. `folder`: the host is told the notes are in `notes/` and has `search_notes` (a regular expression over the
files, like `rg -i`), `list_notes` and `read_note`. `listed`: the same, plus an index in its context, one line per page
(title and path). `krouter`: the session-start standing index as the hook prints it, the hook's note above a message
when it brought a page, `krouter_ask` (the MCP tool's own description; it returns what `route_knowledge.py search`
prints) and `read_note`. The host is `deepseek-flash` through its API with function calling: at most MAX_ROUNDS rounds of
tool calls, then its reply. Each message once, temperature 0. The key is read from the environment and written nowhere.

Set 48 adds: `k1`, krouter with `KROUTER_NEAREST=1` (nearest page titles on a refusal); `k2`, with `KROUTER_TOPICS=1` (the
`krouter_topics` tool and the index's sentence that points to it); `k3`, both; `k4`, krouter as shipped plus the
folder's `search_notes`; and `--mixed`, which writes the distractor pages into the two handbook folders.

Set 49 adds: `--sparse`, a vault whose alias table names few of its pages (every eighth row of the bench table is kept,
no row for a distractor page, trigger words only for the pages still named); and `p1`, krouter with
`KROUTER_INDEX_PAGES=1` (the standing index also lists, by title, the pages in force that the alias table does not name).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"  # 只用 flash，写死；返回的 model 里出现 pro 就停
MAX_TOKENS = 1500
MAX_ROUNDS = 4
WORKERS = 4
SYSTEM_DIR = "90 系统文件/"
BASE = ("You are a coding assistant at a software company, in a session with one user. Reply to the user's message as "
        "you would in that session, in the user's language, in at most six sentences. You have tools; call them only "
        "when this message needs them.")
FOLDER = ("The user's notes on what has been decided (handbook pages and daily logs, Markdown files) are in the folder "
          "`notes/`. `search_notes`, `list_notes` and `read_note` work on that folder.")
LISTED = "Index of the pages in `notes/`, one line per page (title: path):"
KROUTER = "Context the app injected at session start:"
LAST = "[Bench note, not from the user] No more tool calls are available. Write your reply to the user now."
T_SEARCH = {"type": "function", "function": {
    "name": "search_notes",
    "description": "Search the Markdown files under notes/ with a case-insensitive regular expression (like `rg -i`). "
                   "Returns matching lines as path:line: text, at most 30.",
    "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}}
T_LIST = {"type": "function", "function": {
    "name": "list_notes",
    "description": "List the files in a folder under notes/ (empty for the top level). At most 300 names, with the total.",
    "parameters": {"type": "object", "properties": {"folder": {"type": "string"}}}}}
T_READ = {"type": "function", "function": {
    "name": "read_note",
    "description": "Read one Markdown file of the user's notes by its path.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}


class Stop(Exception):
    pass


KCONDS = ("krouter", "k1", "k2", "k3", "k4", "k5", "p1", "h1", "h2")
CANDS = ("h1", "h2")  # 第 51 套：钩子没递页时，随消息附上字面最接近的几页的名字，由宿主判断
SPARSE_EVERY = 8  # set 49: of the bench alias table's rows, in file order, the 1st, 9th, 17th, ... are kept
NEAREST, TOPICS = ("k1", "k3", "k5"), ("k2", "k3", "k5")  # k5: as k3, on the index of the set 48 addendum


def t_topics() -> dict:
    import mcp_server

    d = mcp_server.TOPICS_TOOL
    return {"type": "function", "function": {"name": d["name"], "description": d["description"],
                                             "parameters": d["inputSchema"]}}


def t_ask() -> dict:
    import mcp_server

    d = next(t for t in mcp_server.TOOLS if t["name"] == "krouter_ask")
    return {"type": "function", "function": {
        "name": "krouter_ask", "description": d["description"],
        "parameters": {"type": "object", "properties": {"query": d["inputSchema"]["properties"]["query"]},
                       "required": ["query"]}}}


def pages(v: Path) -> list[str]:
    return sorted(p.relative_to(v).as_posix() for p in v.rglob("*.md")
                  if not p.relative_to(v).as_posix().startswith(SYSTEM_DIR))


def mix_crowd(v: Path) -> None:
    """Set 48: move the distractor pages out of their own folder into the two handbook folders (Chinese names into
    团队手册/, the others into Handbook/) and point their alias rows there."""
    psv = v / "90 系统文件/canonical_sources.psv"
    text = psv.read_text(encoding="utf-8")
    for f in sorted((v / "Archive").glob("*.md")):
        dest = "团队手册" if re.search(r"[\u3400-\u9fff]", f.name) else "Handbook"
        f.rename(v / dest / f.name)
        text = text.replace(f"|Archive/{f.name}|", f"|{dest}/{f.name}|")
    (v / "Archive").rmdir()
    psv.write_text(text, encoding="utf-8")


def make_sparse(v: Path) -> None:
    """Set 49: an alias table nobody kept up. Of the bench table's own rows every SPARSE_EVERY-th is kept (file order,
    from the first); the distractor pages get no row; a trigger-word row stays only when its page is still named."""
    psv = v / "90 系统文件/canonical_sources.psv"
    head, own = [], []
    for line in psv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            head.append(line)
        elif not re.match(r"X\d{3}\|", line):
            own.append(line)
    kept = own[::SPARSE_EVERY]
    psv.write_text("\n".join(head + kept) + "\n", encoding="utf-8")
    named = {row.split("|")[2] for row in kept}
    for f in sorted((v / "90 系统文件/自动化").glob("下意识触发词*.psv")):
        rows = [x for x in f.read_text(encoding="utf-8").splitlines()
                if not x.strip() or x.startswith("#") or x.split("|")[0] in named]
        f.write_text("\n".join(rows) + "\n", encoding="utf-8")


def prepare(work: Path, crowd: int, mixed: bool = False, sparse: bool = False) -> None:
    import shutil

    import both
    import run as set32
    import set45

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    os.environ.update(both.env_for(work))
    v = set32.make_vault(work)
    if crowd:
        both.add_crowd(v, crowd, newer=True)
        if mixed:
            mix_crowd(v)
    if sparse:
        make_sparse(v)
    import compile_subconscious
    import recall_index
    import recollect

    recall_index.recall(v, "warm up")
    index = compile_subconscious.standing_index(v)
    os.environ["KROUTER_TOPICS"] = "1"
    index_topics = compile_subconscious.standing_index(v)
    del os.environ["KROUTER_TOPICS"]
    os.environ["KROUTER_INDEX_PAGES"] = "1"
    index_pages = compile_subconscious.standing_index(v)
    del os.environ["KROUTER_INDEX_PAGES"]
    lines = []
    for rel in pages(v):
        got = recollect.page(v, rel)
        lines.append(f"- {(got[0].get('title') if got else '') or Path(rel).stem}: notes/{rel}")
    import candidates

    items, key = [], {}
    for r in set45.case_file("set45dev"):
        hits = recollect.recollect(v, r["text"], recollect.DEFAULT_ROUTES)
        note = recollect.render(hits)
        cands = candidates.candidates(v, r["text"], {h["real"] for h in hits}, candidates.K_HOST)
        with_c = "\n\n".join(x for x in (note, candidates.render(cands, r["lang"])) if x)
        tpl, nt = (both.ZH, both.ZH_NOTE) if r["lang"] == "zh" else (both.EN, both.EN_NOTE)
        items.append({"id": r["id"], "plain": tpl.format(note="", text=r["text"]),
                      "krouter": tpl.format(note=nt.format(note=note) if note else "", text=r["text"]),
                      "krouter_c": tpl.format(note=nt.format(note=with_c) if with_c else "", text=r["text"])})
        key[r["id"]] = {**r, "hook": [h["real"] for h in hits], "cand": [c["real"] for c in cands]}
    (work / "prep.json").write_text(json.dumps({"index": index, "index_topics": index_topics, "index_pages": index_pages, "listed": "\n".join(lines),
                                                "items": items},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} items; {len(lines)} pages; standing index {len(index)} characters; page list "
          f"{len(chr(10).join(lines))} characters; the hook brought a page for {sum(bool(k['hook']) for k in key.values())}; "
          f"candidates go with {sum(bool(k['cand']) for k in key.values())}")


def system(prep: dict, cond: str) -> str:
    if cond == "folder":
        return f"{BASE}\n\n{FOLDER}"
    if cond == "listed":
        return f"{BASE}\n\n{FOLDER}\n\n{LISTED}\n{prep['listed']}"
    which = "index_pages" if cond in ("p1", "h2") else ("index_topics" if cond in TOPICS else "index")
    return f"{BASE}\n\n{KROUTER}\n{prep[which]}"


def rel_of(work: Path, path: str) -> str:
    v = work / "vault"
    p = (path or "").strip().strip("`'\"〔〕[]")
    for pre in (str(v) + "/", "notes/", "./notes/", "/notes/", "./"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p if p and (v / p).is_file() and not p.startswith(SYSTEM_DIR) else ""


def tool(work: Path, name: str, args: dict, cond: str = "krouter") -> str:
    v = work / "vault"
    if name == "read_note":
        rel = rel_of(work, str(args.get("path", "")))
        return (v / rel).read_text(encoding="utf-8")[:4000] if rel else "no such file"
    if name == "list_notes":
        d = str(args.get("folder") or "").strip().strip("/")
        d = d[6:] if d.startswith("notes/") else ("" if d == "notes" else d)
        base = v / d
        if not base.is_dir() or d.startswith(SYSTEM_DIR.strip("/")):
            return "no such folder"
        names = sorted((x.name + "/") if x.is_dir() else x.name for x in base.iterdir()
                       if not (x.relative_to(v).as_posix() + "/").startswith(SYSTEM_DIR))
        return f"{len(names)} entries in notes/{d}\n" + "\n".join(names[:300])
    if name == "search_notes":
        pat = str(args.get("pattern") or "")
        try:
            rx = re.compile(pat, re.I)
        except re.error:
            rx = re.compile(re.escape(pat), re.I)
        out, files = [], set()
        for rel in pages(v):
            for n, line in enumerate((v / rel).read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    files.add(rel)
                    if len(out) < 30:
                        out.append(f"notes/{rel}:{n}: {line[:200]}")
        return f"{len(files)} files match\n" + "\n".join(out) if out else "no match"
    if name == "krouter_ask":
        import both

        q = str(args.get("query") or "").strip()
        if not q:
            return "query is required"
        env = {**both.env_for(work), **({"KROUTER_NEAREST": "1"} if cond in NEAREST else {})}
        return subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], env=env,
                              capture_output=True, text=True, timeout=60).stdout[:4000] or "recall: none"
    if name == "krouter_topics" and cond in TOPICS:
        import both

        return subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "topics", str(args.get("group") or "")],
                              env={**both.env_for(work), "KROUTER_TOPICS": "1"}, capture_output=True, text=True,
                              timeout=60).stdout[:60000] or "no topics"
    return f"unknown tool {name}"


def call(msgs: list[dict], tools: list[dict] | None, key: str) -> dict:
    body = {"model": MODEL, "messages": msgs, "temperature": 0, "max_tokens": MAX_TOKENS}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "bench-client"})
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
    if "pro" in d.get("model", "").lower():
        raise Stop(json.dumps({"unexpected_model": d.get("model")}))
    return d


def converse(work: Path, prep: dict, cond: str, item: dict, key: str) -> dict:
    if cond in KCONDS:
        tools = [t_ask(), T_READ] + ([t_topics()] if cond in TOPICS else []) + ([T_SEARCH] if cond == "k4" else [])
    else:
        tools = [T_SEARCH, T_LIST, T_READ]
    msgs = [{"role": "system", "content": system(prep, cond)},
            {"role": "user", "content": item["krouter_c" if cond in CANDS else "krouter" if cond in KCONDS else "plain"]}]
    calls, use, model, finish = [], Counter(), "", ""
    for rnd in range(MAX_ROUNDS + 1):
        if rnd == MAX_ROUNDS:
            msgs.append({"role": "user", "content": LAST})
        d = call(msgs, tools if rnd < MAX_ROUNDS else None, key)
        model = d.get("model", "")
        for k in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens"):
            use[k] += (d.get("usage") or {}).get(k) or 0
        ch = d["choices"][0]
        m, finish = ch["message"], ch.get("finish_reason")
        tcs = m.get("tool_calls") or []
        if not tcs or rnd == MAX_ROUNDS:
            return {"id": item["id"], "response": m.get("content") or "", "calls": calls, "rounds": rnd, "model": model,
                    "finish_reason": finish, "usage": dict(use)}
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": tcs})
        for tc in tcs:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append({"name": fn.get("name"), "args": args})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": tool(work, fn.get("name", ""), args, cond)})
    raise AssertionError("unreachable")


def run(work: Path, cond: str) -> int:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    prep = json.loads((work / "prep.json").read_text(encoding="utf-8"))
    out = work / f"replies_{cond}.jsonl"
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()} if out.exists() else set()
    todo = [i for i in prep["items"] if i["id"] not in done]
    lock, flag = threading.Lock(), {"stop": None}

    def one(item: dict) -> None:
        if flag["stop"]:
            return
        try:
            rec = converse(work, prep, cond, item, key)
        except Stop as e:
            flag["stop"] = f"{item['id']} {e}"
            return
        with lock:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()] if out.exists() else []
    tok = Counter()
    for r in rows:
        tok.update(r.get("usage") or {})
    print(json.dumps({"cond": cond, "items": len(prep["items"]), "replies": len(rows),
                      "models": sorted({r.get("model") for r in rows}),
                      "not_stop": sum(r.get("finish_reason") != "stop" for r in rows), "tokens": dict(tok),
                      "stopped": flag["stop"]}, ensure_ascii=False))
    return 1 if flag["stop"] else 0


def host_pages(work: Path, rec: dict, every: list[str]) -> list[str]:
    """Pages the host read, got first from krouter_ask (set 35's rule), or named in its reply."""
    import both

    out = []
    for c in rec["calls"]:
        p = ""
        if c["name"] == "read_note":
            p = rel_of(work, str(c["args"].get("path", "")))
        elif c["name"] == "krouter_ask":
            p = both.resolve(work, "krouter_ask", str(c["args"].get("query", "")))
        if p and p not in out:
            out.append(p)
    reply = rec["response"]
    for rel in sorted(every, key=len, reverse=True):
        if (rel in reply or rel[:-3] in reply or Path(rel).name in reply) and rel not in out:
            out.append(rel)
    return out


def score(work: Path, cond: str) -> int:
    key = json.loads((work / "key.json").read_text(encoding="utf-8"))
    every = pages(work / "vault")
    rows = {j["id"]: j for j in map(json.loads, (work / f"replies_{cond}.jsonl").read_text(encoding="utf-8").splitlines()) if j}
    c: Counter = Counter()
    detail = {}
    for cid, k in key.items():
        r = rows.get(cid)
        if r is None:
            c["missing"] += 1
            continue
        hook = k["hook"] if cond in KCONDS else []
        hp = host_pages(work, r, every)
        n = len(r["calls"])
        detail[cid] = {"hook": hook, "host": hp, "calls": [x["name"] for x in r["calls"]]}
        c["calls"] += n
        c["prompt_tokens"] += r["usage"].get("prompt_tokens", 0)
        c["completion_tokens"] += r["usage"].get("completion_tokens", 0)
        c[f"calls_{k['kind']}"] += n
        c[f"looked_{k['kind']}"] += bool(n)
        if k["kind"] == "quiet":
            c["quiet_n"] += 1
            reply = r["response"]
            c["quiet_names_page"] += any(rel in reply or rel[:-3] in reply or Path(rel).name in reply for rel in every)
            if hook or hp or n:
                c["quiet_loud"] += 1
                c[f"loud_{k.get('subkind')}"] += 1
            continue
        kind = k["kind"]
        c[f"{kind}_n"] += 1
        named = "named" if k.get("named_mech") else "unnamed"
        c[f"{kind}_{named}_n"] += 1
        right = k["expect"] in hook or k["expect"] in hp
        c[f"{kind}_right"] += right
        c[f"{kind}_{named}_right"] += right
        c[f"{kind}_right_{k['lang']}"] += right
        c["wrong"] += len([p for p in set(hook) | set(hp) if p != k["expect"]])
        c["old"] += bool(k.get("old") and k["old"] in set(hook) | set(hp))
        c["old_read"] += bool(k.get("old") and any(x["name"] == "read_note" and rel_of(work, str(x["args"].get("path", "")))
                                                   == k["old"] for x in r["calls"]))
    n = len(rows) or 1
    print(f"{cond}: items {len(key)} missing {c['missing']}")
    print(f"  recall {c['recall_right']}/{c['recall_n']} (unnamed {c['recall_unnamed_right']}/{c['recall_unnamed_n']}, named "
          f"{c['recall_named_right']}/{c['recall_named_n']}; zh {c['recall_right_zh']}, en {c['recall_right_en']})  changed "
          f"{c['changed_right']}/{c['changed_n']}  quiet loud {c['quiet_loud']}/{c['quiet_n']}  wrong {c['wrong']}  old {c['old']}")
    print("  quiet loud by kind: " + ", ".join(f"{s}={c.get('loud_' + s, 0)}/8" for s in (
        "unrelated", "other_sense", "common_word", "pasted", "near_topic", "ack")))
    print(f"  tool calls {c['calls']} ({c['calls'] / n:.2f} a message; recall {c['calls_recall']}, changed {c['calls_changed']}, "
          f"quiet {c['calls_quiet']}); messages with a call: recall {c['looked_recall']}/48, changed {c['looked_changed']}/24, "
          f"quiet {c['looked_quiet']}/48")
    print(f"  replaced page read with read_note: {c['old_read']} of {c['changed_n']} changed cases")
    print(f"  quiet messages whose reply names a vault page: {c['quiet_names_page']}/{c['quiet_n']}; calls by tool: "
          + ", ".join(f"{k} {v}" for k, v in sorted(Counter(x["name"] for r in rows.values() for x in r["calls"]).items())))
    print(f"  tokens: {c['prompt_tokens']} in, {c['completion_tokens']} out ({c['prompt_tokens'] / n:.0f} in a message)")
    (work / f"detail_{cond}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


JUDGE = """A user sent a message to a coding assistant. The team's handbook has a page that settles what the message is about.

Page in force:
{page}
{old}
Assistant's reply:
{reply}

Answer with one JSON object and nothing else: {{"carries": true or false, "old": true or false}}
"carries": the reply states, as the team's rule, the thing the page in force says (its specific value, limit, tool or step), not just that a page exists or will be looked up.
"old": the reply states the replaced page's rule as if it were still the rule (false when there is no replaced page)."""


def judge(work: Path, cond: str) -> int:
    apikey = os.environ.get("DEEPSEEK_API_KEY", "")
    key = json.loads((work / "key.json").read_text(encoding="utf-8"))
    rows = {j["id"]: j for j in map(json.loads, (work / f"replies_{cond}.jsonl").read_text(encoding="utf-8").splitlines()) if j}
    out = work / f"judge_{cond}.jsonl"
    done = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()} if out.exists() else set()
    v = work / "vault"
    todo = [cid for cid, k in key.items() if k["kind"] != "quiet" and cid in rows and cid not in done]
    lock = threading.Lock()

    def one(cid: str) -> None:
        k = key[cid]
        old = f"\nReplaced page (no longer the rule):\n{(v / k['old']).read_text(encoding='utf-8')}\n" if k.get("old") else ""
        p = JUDGE.format(page=(v / k["expect"]).read_text(encoding="utf-8"), old=old, reply=rows[cid]["response"] or "(empty)")
        d = call([{"role": "user", "content": p}], None, apikey)
        text = d["choices"][0]["message"].get("content") or ""
        m = re.search(r"\{.*\}", text, re.S)
        try:
            j = json.loads(m.group(0)) if m else {}
        except ValueError:
            j = {}
        with lock:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": cid, "carries": j.get("carries"), "old": j.get("old"), "raw": text[:200]},
                                    ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    c: Counter = Counter()
    for j in map(json.loads, out.read_text(encoding="utf-8").splitlines()):
        kind = key[j["id"]]["kind"]
        c[f"{kind}_n"] += 1
        c[f"{kind}_carries"] += j["carries"] is True
        c[f"{kind}_old"] += j["old"] is True
        c["unread"] += j["carries"] not in (True, False)
    print(f"{cond}: reply carries the page's rule (judge): recall {c['recall_carries']}/{c['recall_n']}, changed "
          f"{c['changed_carries']}/{c['changed_n']}; states the replaced rule as current: {c['changed_old']}/{c['changed_n']}; "
          f"verdicts not read {c['unread']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "run", "score", "judge"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--cond", default="krouter", choices=["folder", "listed", *KCONDS])
    ap.add_argument("--crowd", type=int, default=0)
    ap.add_argument("--mixed", action="store_true")
    ap.add_argument("--sparse", action="store_true")
    a = ap.parse_args()
    work = Path(a.work)
    if a.cmd == "prepare":
        prepare(work, a.crowd, a.mixed, a.sparse)
        return 0
    return {"run": run, "score": score, "judge": judge}[a.cmd](work, a.cond)


if __name__ == "__main__":
    raise SystemExit(main())
