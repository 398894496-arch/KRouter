#!/usr/bin/env python3
"""Sets 35 and 36 (bench/memory_honesty/HELDOUT.md): the prompt hook, then the host reading the standing index.

    python3 bench/subconscious/both.py prepare dev --work DIR [--crowd N] [--crowd-capped]   # DIR/batch.json, DIR/key.json
    (a subagent on the named model answers every item into DIR/replies_<host>.jsonl {id, response})
    python3 bench/subconscious/both.py score --work DIR --host haiku [--show]
    python3 bench/subconscious/both.py learn --work DIR --host sonnet        # set 36, after a `prepare learn` run

The bench vault (vault3 + overlay, plus `--crowd` distractor topics) is built once in DIR at `prepare` and kept, because
the host's fetches name its paths and `score` runs each fetch on it for real: `CALL krouter_ask: <question>` and
`CALL shell: … route_knowledge.sh search '<q>'` resolve to the lock's page, else recall's first page when recall answers;
`CALL read: <path>` to that path. A page whose path the reply names counts as recalled too.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
import run as set32  # noqa: E402

ZH = "{note}【用户消息】\n{text}"
ZH_NOTE = "【这一轮，应用的钩子随用户消息附上的上下文（用户看不到）】\n{note}\n\n"
EN = "{note}[User message]\n{text}"
EN_NOTE = "[Context the app's hook attached to this user message this turn (the user does not see it)]\n{note}\n\n"
INSTRUCTIONS = (
    "Each item below is a separate session with a coding assistant at a software company. Every session began with the "
    "same context, injected by the app at session start; it is in `context`. Then the user sent the item's message "
    "(sometimes with context the app attached to that message). Reply to each item as you would in that session, as "
    "if it were the only one: only the start of the reply, at most four sentences, in the user's language. Do not run "
    "anything or call tools. If you would fetch something first (a tool call, a command, reading a file), write each "
    "such fetch as its own first line, exactly `CALL krouter_ask: <question>`, `CALL shell: <command>` or "
    "`CALL read: <path>`, then the reply.")


def env_for(work: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(KROUTER_VAULT=str(work / "vault"), KROUTER_CACHE_DIR=str(work / "cache"),
               KROUTER_STATE_DIR=str(work / "state"), KROUTER_NO_QUERY_LOG="1")
    env.pop("OBSIDIAN_VAULT", None)
    return env


def cases(split: str) -> list[dict]:
    if split == "dev":
        text = (HERE / "set35_dev.jsonl").read_text(encoding="utf-8")
    elif split == "heldout":
        text = gzip.decompress((HERE / "set35_heldout.jsonl.gz").read_bytes()).decode("utf-8")
    elif split in ("set45dev", "set45held"):
        import set45

        return set45.case_file(split)
    elif split == "learn":
        rows = [json.loads(x) for x in (HERE / "set36.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        return [{"id": r["id"], "lang": r["lang"], "kind": "recall", "text": r["first"], "expect": r["expect"]}
                for r in rows if r["kind"] == "pair"]
    else:
        raise SystemExit(f"unknown split {split}")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


CROWD_ZH = "温室 番茄 剪枝 茶叶 发酵 帆船 露营 陶艺 烘焙 盆栽 钓鱼 登山 滑雪 刺绣 书法 围棋 骑行 养蜂 酿酒 插花".split()
CROWD_EN = ("greenhouse tomato pruning tea fermenting sailing camping pottery baking bonsai fishing hiking skiing "
            "embroidery calligraphy chess cycling beekeeping brewing flowers").split()


def add_crowd(v: Path, n: int, newer: bool) -> None:
    """n distractor topics on hobbies no case touches: a page each and an alias row, dated after (newer) or before the
    real pages."""
    rnd = random.Random(20261135)
    psv = v / "90 系统文件/canonical_sources.psv"
    rows = []
    for i in range(n):
        zh = i % 2 == 0
        a, b = (rnd.sample(CROWD_ZH, 2) if zh else rnd.sample(CROWD_EN, 2))
        name = f"{a}{b}{i:03d}" if zh else f"{a} {b} {i:03d}"
        rel = f"Archive/{name}.md"
        day = f"2026-10-{1 + i % 28:02d}" if newer else f"2025-0{1 + i % 9}-{1 + i % 28:02d}"
        body = (f"{a}的{b}每周做两次，第 {i} 号记录。" if zh else f"The {a} {b} routine runs twice a week, record {i}.")
        (v / "Archive").mkdir(exist_ok=True)
        (v / rel).write_text(f"---\ntitle: {name}\nstatus: active\ndate: {day}\n---\n\n# {name}\n\n{body}\n", encoding="utf-8")
        rows.append(f"X{i:03d}|{name}|{rel}|{body}")
    with psv.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")


def prepare(split: str, work: Path, crowd: int, capped: bool) -> None:
    import shutil

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    env = env_for(work)
    os.environ.update(env)
    v = set32.make_vault(work)
    if crowd:
        add_crowd(v, crowd, newer=capped)
    import compile_subconscious
    import recall_index
    import recollect

    recall_index.recall(v, "warm up")
    lines, chars = (compile_subconscious.INDEX_LINES, compile_subconscious.INDEX_CHARS) if (capped or not crowd) \
        else (100000, 10 ** 7)
    index = compile_subconscious.standing_index(v, lines=lines, chars=chars)
    rows = cases(split)
    items, key = [], {}
    for r in rows:
        hits = recollect.recollect(v, r["text"], recollect.DEFAULT_ROUTES)
        note = recollect.render(hits)
        tpl, nt = (ZH, ZH_NOTE) if r["lang"] == "zh" else (EN, EN_NOTE)
        pid = hashlib.sha1(f"{split}|{r['id']}".encode()).hexdigest()[:10]
        items.append({"id": pid, "message": tpl.format(note=nt.format(note=note) if note else "", text=r["text"])})
        key[pid] = {**r, "hook": [h["real"] for h in hits]}
    random.Random(20261136).shuffle(items)
    listed = [x["rel"] for x in compile_subconscious.index_topics(v)]  # 索引里的每个主题（整行或只列名字）
    (work / "batch.json").write_text(json.dumps({"instructions": INSTRUCTIONS, "context": index, "items": items},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "listed.json").write_text(json.dumps(listed, ensure_ascii=False), encoding="utf-8")
    import compile_subconscious as cs

    full = len(re.findall(r"^- ", index, re.M))
    print(f"{len(items)} items; index {len(index)} characters, about {cs.est_tokens(index)} tokens, {len(listed)} topics, "
          f"{full} as full lines")


CALL = re.compile(r"^\s*[`*>-]*\s*CALL\s+(krouter_ask|shell|read)\s*[:：]\s*(.+?)\s*`?\s*$", re.M | re.I)


def resolve(work: Path, kind: str, arg: str) -> str:
    vault = work / "vault"
    arg = arg.strip().strip("`").strip()
    if kind.lower() == "read":
        p = arg.strip("'\"")
        if p.startswith(str(vault)):
            p = p[len(str(vault)) + 1:]
        return p if (vault / p).is_file() else ""
    q = arg.strip("'\"")
    if kind.lower() == "shell":
        if "route_knowledge" not in arg:
            m = re.search(re.escape(str(vault)) + r"/([^'\"]+\.md)", arg)
            return m.group(1) if m and (vault / m.group(1)).is_file() else ""
        try:
            parts = shlex.split(arg)
        except ValueError:
            parts = arg.split()
        q = parts[-1] if parts else ""
    q = re.sub(r"^(question|query)\s*=\s*", "", q).strip("'\"()")
    out = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], env=env_for(work),
                         capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"canonical_source:\s*(.+\.md)", out)
    if m:
        return m.group(1).strip()[len(str(vault)) + 1:]
    if "recall:" in out and "recall_confidence: none" not in out:
        m = re.search(r"^recall:\n- (.+?\.md) tier=", out, re.M)
        if m:
            return m.group(1)
    return ""


def memory_fetch(work: Path, kind: str, arg: str) -> bool:
    """A fetch from the memory: krouter_ask, the route command, or reading a file inside the vault. Reading the
    project's own files (`package.json`) is ordinary work, not a memory fetch (set 35's log, before held-out)."""
    k = kind.lower()
    return k == "krouter_ask" or (k == "shell" and ("route_knowledge" in arg or str(work / "vault") in arg)) or \
        (k == "read" and (str(work / "vault") in arg or (work / "vault" / arg.strip().strip("'\"`")).is_file()))


def host_pages(work: Path, reply: str, listed: list[str]) -> tuple[list[str], int]:
    """(pages the reply fetched or named, number of memory fetches)."""
    calls = [(k, a) for k, a in CALL.findall(reply) if memory_fetch(work, k, a)]
    pages = []
    for kind, arg in calls:
        p = resolve(work, kind, arg)
        if p and p not in pages:
            pages.append(p)
    every = sorted({p for p in listed} | set(pages), key=len, reverse=True)
    for rel in every:
        stem, name = rel[:-3], Path(rel).name
        if (rel in reply or stem in reply or name in reply) and rel not in pages:
            pages.append(rel)
    return pages, len(calls)


def score(work: Path, host: str, show: bool) -> dict:
    key = json.loads((work / "key.json").read_text(encoding="utf-8"))
    listed = json.loads((work / "listed.json").read_text(encoding="utf-8"))
    rep = {}
    for line in (work / f"replies_{host}.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            j = json.loads(line)
            rep[j["id"]] = j.get("response", "")
    c: Counter = Counter()
    detail = {}
    for pid, k in key.items():
        r = rep.get(pid)
        if r is None:
            c["missing"] += 1
            continue
        L = k["lang"]
        hp, ncalls = host_pages(work, r, listed)
        hook = k["hook"]
        detail[pid] = {"case": k["id"], "hook": hook, "host": hp, "calls": ncalls}
        if k["kind"] == "quiet":
            c[f"quiet_n_{L}"] += 1
            if hook or hp or ncalls:
                c[f"quiet_loud_{L}"] += 1
                c[f"loud_{k.get('subkind')}"] += 1
                c[f"quiet_loud_hook_{L}"] += bool(hook)
            continue
        kind = k["kind"]
        c[f"{kind}_n_{L}"] += 1
        named = "named" if k.get("named_mech", k.get("named")) else "unnamed"
        c[f"{kind}_{named}_n_{L}"] += 1
        right_hook = k["expect"] in hook
        right_host = k["expect"] in hp
        if right_hook or right_host:
            c[f"{kind}_right_{L}"] += 1
            c[f"{kind}_{named}_right_{L}"] += 1
            c[f"{kind}_by_hook_{L}"] += right_hook
            c[f"{kind}_by_host_{L}"] += (right_host and not right_hook)
        wrong = [p for p in set(hook) | set(hp) if p != k["expect"]]
        c[f"wrong_{L}"] += len(wrong)
        c[f"wrong_hook_{L}"] += len([p for p in set(hook) if p != k["expect"]])
        c[f"wrong_host_{L}"] += len([p for p in set(hp) if p != k["expect"] and p not in hook])
        if k.get("old") and k["old"] in set(hook) | set(hp):
            c[f"old_{L}"] += 1
        if show and (wrong or not (right_hook or right_host)):
            print(f"✗ {k['id']} expect={k['expect']} hook={hook} host={hp} calls={ncalls}\n    {k['text'][:160]!r}\n"
                  f"    reply: {r[:240]!r}")
    if show:
        for pid, k in key.items():
            d = detail.get(pid)
            if d and k["kind"] == "quiet" and (d["hook"] or d["host"] or d["calls"]):
                print(f"✗ {k['id']} [{k.get('subkind')}] hook={d['hook']} host={d['host']} calls={d['calls']}\n"
                      f"    {k['text'][:160]!r}\n    reply: {rep[pid][:240]!r}")
    g = lambda name: c.get(f"{name}_zh", 0) + c.get(f"{name}_en", 0)
    print(f"{host}: items {len(key)} missing {c['missing']}")
    for L in ("zh", "en"):
        print(f"  {L}: recall {c[f'recall_right_{L}']}/{c[f'recall_n_{L}']} (hook {c[f'recall_by_hook_{L}']}, host "
              f"{c[f'recall_by_host_{L}']}; unnamed {c[f'recall_unnamed_right_{L}']}/{c[f'recall_unnamed_n_{L}']})  "
              f"changed {c[f'changed_right_{L}']}/{c[f'changed_n_{L}']} (hook {c[f'changed_by_hook_{L}']}, host "
              f"{c[f'changed_by_host_{L}']})  quiet-loud {c[f'quiet_loud_{L}']}/{c[f'quiet_n_{L}']} "
              f"(hook {c[f'quiet_loud_hook_{L}']})  wrong {c[f'wrong_{L}']}  old {c[f'old_{L}']}")
    print(f"  all: recall {g('recall_right')}/{g('recall_n')}  changed {g('changed_right')}/{g('changed_n')}  "
          f"quiet-loud {g('quiet_loud')}/{g('quiet_n')}  wrong {g('wrong')}  old {g('old')}  loud by kind: "
          + ", ".join(f"{s}={c.get('loud_' + s, 0)}" for s in ("unrelated", "other_sense", "common_word", "pasted")))
    if any(k.get("subkind") in ("near_topic", "ack") for k in key.values()):
        print("  set 45 layers (recall, both languages): hook alone " + str(g("recall_by_hook")) + ", host where the hook was not "
              + str(g("recall_by_host")) + ", both layers " + str(g("recall_right")) + f" of {g('recall_n')}; unnamed "
              f"{g('recall_unnamed_right')}/{g('recall_unnamed_n')}, named {g('recall_named_right')}/{g('recall_named_n')}")
        print("  changed: hook alone " + str(g("changed_by_hook")) + ", host where the hook was not " + str(g("changed_by_host"))
              + ", both " + str(g("changed_right")) + f" of {g('changed_n')}")
        print("  quiet loud by the six kinds: " + ", ".join(
            f"{s}={c.get('loud_' + s, 0)}/8" for s in ("unrelated", "other_sense", "common_word", "pasted", "near_topic", "ack")))
        print(f"  wrong pages: by the hook {g('wrong_hook')}, by the host only {g('wrong_host')}; old-page deliveries {g('old')}")
    (work / f"detail_{host}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(c)


def learn(work: Path, host: str) -> None:
    """Set 36: learning events from the host's replies on the first messages, the nightly step, then the hook alone on
    the second messages, the lookalikes and set 35's held-out quiet messages, before and after."""
    import learn_mentions
    import recollect

    os.environ.update(env_for(work))
    v = work / "vault"
    key = json.loads((work / "key.json").read_text(encoding="utf-8"))
    listed = json.loads((work / "listed.json").read_text(encoding="utf-8"))
    rep = {j["id"]: j.get("response", "") for j in map(json.loads, (work / f"replies_{host}.jsonl").read_text(
        encoding="utf-8").splitlines()) if j}
    pairs = {r["id"]: r for r in map(json.loads, (HERE / "set36.jsonl").read_text(encoding="utf-8").splitlines()) if r}
    quiet = [r["text"] for r in pairs.values() if r["kind"] == "lookalike"]
    quiet += [r["text"] for r in cases("heldout") if r["kind"] == "quiet"]
    seconds = [(r["id"], r["second"], r["expect"]) for r in pairs.values() if r["kind"] == "pair"]

    def hook(text):
        recollect._ENTRIES.clear()
        recollect._PAGES.clear()
        return [h["real"] for h in recollect.recollect(v, text, recollect.DEFAULT_ROUTES)]

    before = {i: hook(t) for i, t, _ in seconds}
    q_before = sum(bool(hook(t)) for t in quiet)
    state = work / "state"
    state.mkdir(exist_ok=True)
    events = []
    for pid, k in key.items():
        hp, _n = host_pages(work, rep.get(pid, ""), listed)
        if not k["hook"] and k["expect"] in hp:
            events.append({"ts": "", "kind": "learn", "agent": host, "session": pid[:8],
                           "sentence": recollect.cut(recollect.redact(recollect.prose(k["text"])), 300), "page": k["expect"],
                           "case": k["id"]})
    (state / recollect.LEARN_LOG).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
                                             encoding="utf-8")
    out = learn_mentions.run(v, state)
    import recall_index

    recall_index.recall(v, "refresh after the trigger file changed")
    after = {i: hook(t) for i, t, _ in seconds}
    q_after = sum(bool(hook(t)) for t in quiet)
    learned = {e["case"] for e in events}
    for lang in ("zh", "en"):
        ids = [i for i, _t, _e in seconds if i.startswith(lang)]
        el = [i for i in ids if i in learned]
        exp = {i: e for i, _t, e in seconds}
        print(f"  {lang}: pairs {len(ids)}, learning events {len(el)}; second message right by the hook alone: "
              f"before {sum(exp[i] in before[i] for i in ids)}/{len(ids)}, after {sum(exp[i] in after[i] for i in ids)}/{len(ids)} "
              f"(of those with an event: {sum(exp[i] in after[i] for i in el)}/{len(el)}); wrong after "
              f"{sum(len([p for p in after[i] if p != exp[i]]) for i in ids)}")
    print(f"  quiet ({len(quiet)}: lookalikes + set 35 held-out quiet) bringing something: before {q_before}, after {q_after}")
    print("  learned:", json.dumps([(a["page"], a["phrase"]) for a in out["added"]], ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "score", "learn"])
    ap.add_argument("split", nargs="?", default="dev")
    ap.add_argument("--work", required=True)
    ap.add_argument("--host", default="")
    ap.add_argument("--crowd", type=int, default=0)
    ap.add_argument("--crowd-capped", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    work = Path(a.work)
    if a.cmd == "prepare":
        prepare(a.split, work, a.crowd, a.crowd_capped)
    elif a.cmd == "score":
        score(work, a.host, a.show)
    else:
        learn(work, a.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
