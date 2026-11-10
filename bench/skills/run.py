#!/usr/bin/env python3
"""Sets 24–26 (bench/memory_honesty/HELDOUT.md): experience growing into skills.

Set 24, drafting: does the nightly drafting step draft a skill where it should, stay faithful to the cards it rests
on, and draft nothing where it should not? Each scenario is a small vault of experience cards with use counts. The
prompt is exactly what `skills.draft_step` sends through the host lane (`skills.prompt`); a host model answers it, and
the reply goes through `skills.parse` (the code's own checks) as the nightly run would.

Set 25, use: given the session-start digest with skills (`skills.digest`) and the `krouter_skill` tool, does the host
fetch the right skill on a task it fits and follow its steps, and stay quiet on a task it does not fit? Two phases:
the host decides whether to call the tool; where it calls, it gets the full text (`skills.show`) and replies.

Set 26, adoption: after a reply that followed a skill, does the use record (`experience.uses_in`, the same code as
for cards) say `adopted` only when the user's next message says so? The development half picks the promotion and
withdrawal thresholds by the rule registered in HELDOUT.md; the held-out half is reported once.

Hosts run as sets 15–23 ran theirs: this script writes prompt batches, a Claude Code subagent on the named model
answers each prompt in a batch as if it were the only one and writes the replies back, and this script scores them.

    python3 bench/skills/run.py split --set 24 --raw RAW.jsonl          # once, at seed 2026112400 + set
    python3 bench/skills/run.py prepare24 dev --out DIR
    python3 bench/skills/run.py score24 dev --replies DIR/replies_haiku [--judge-out J] [--verdicts V]
    python3 bench/skills/run.py prepare25 dev --out DIR
    python3 bench/skills/run.py phase2 dev --calls DIR/replies_haiku --out DIR2
    python3 bench/skills/run.py score25 dev --calls DIR/replies_haiku --replies DIR2/replies_haiku [--judge-out J] [--verdicts V]
    python3 bench/skills/run.py score26 dev
    python3 bench/skills/run.py thresholds --p-true X --p-false Y
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
os.environ.setdefault("KROUTER_SKILLS", "1")
os.environ.setdefault("KROUTER_NO_QUERY_LOG", "1")
import experience  # noqa: E402
import skills  # noqa: E402

BATCH = 16


def opaque(set_id: str, case_id: str, n: int = 8, prefix: str = "q") -> str:
    return prefix + hashlib.sha1(f"set{set_id}:{case_id}".encode("utf-8")).hexdigest()[:n]


# ---------- 切分 ----------

def split(args) -> None:
    rows = [json.loads(x) for x in Path(args.raw).read_text(encoding="utf-8").splitlines() if x.strip()]
    rng = random.Random(2026112400 + int(args.set))
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["kind"], r.get("lang", "zh")), []).append(r)
    dev, held = [], []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda r: r["id"])
        rng.shuffle(g)
        half = len(g) // 2 + (len(g) % 2 and rng.random() < 0.5)
        dev += g[:half]
        held += g[half:]
    (HERE / f"set{args.set}_dev.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in dev),
                                                    encoding="utf-8")
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in held)
    with gzip.open(HERE / f"set{args.set}_heldout.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(text)
    print(json.dumps({"dev": len(dev), "heldout": len(held), "kinds_dev": Counter(r["kind"] for r in dev),
                      "kinds_heldout": Counter(r["kind"] for r in held),
                      "sha256_heldout_text": hashlib.sha256(text.encode("utf-8")).hexdigest()}, ensure_ascii=False))


def load(set_id: str, split_name: str) -> list[dict]:
    if split_name == "dev":
        text = (HERE / f"set{set_id}_dev.jsonl").read_text(encoding="utf-8")
    else:
        with gzip.open(HERE / f"set{set_id}_heldout.jsonl.gz", "rt", encoding="utf-8") as fh:
            text = fh.read()
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def write_batches(rows: list[dict], out: Path, size: int = BATCH) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for i in range(0, len(rows), size):
        n += 1
        (out / f"batch_{n:02d}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                          for r in rows[i:i + size]), encoding="utf-8")
    return n


def read_replies(folder: Path) -> dict[str, str]:
    out = {}
    for f in sorted(Path(folder).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["id"]] = d.get("response", "")
    return out


# ---------- 第 24 套：起草 ----------

def card_ids(s: dict) -> dict[str, str]:
    """The writer's card keys → opaque card ids (the kind of scenario is not in an id)."""
    return {c["key"]: opaque("24", s["id"] + ":" + c["key"], 4, "E") for c in s["cards"]}


def build24(root: Path, s: dict) -> Path:
    vault = root / "vault"
    shutil.copytree(REPO / ("template-zh" if s.get("lang", "zh") == "zh" else "template"), vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    ids = card_ids(s)
    uses = []
    for c in s["cards"]:
        cid = ids[c["key"]]
        zh = s.get("lang", "zh") == "zh"
        body = (f"- 处境：{c['situation']}\n- 做法：{c['action']}\n- 结果：{c['result']}\n- 通用说法：{c['lesson']}\n" if zh else
                f"- Situation: {c['situation']}\n- Action: {c['action']}\n- Result: {c['result']}\n- Lesson: {c['lesson']}\n")
        title = c["lesson"].split("，")[0].split(",")[0][:30]
        (folder / f"{cid}.md").write_text(
            f"---\ntitle: \"{'经验｜' if zh else 'Lesson: '}{title}\"\ntype: experience-card\nstatus: provisional\n"
            f"card_id: {cid}\nsource_ref: \"[[05 时间日志/会话摘录/bench｜{cid}]]\"\ndate: 2026-10-01\nsource: bench\n---\n\n"
            f"# {title}\n\n{body}", encoding="utf-8")
        for i in range(int(c.get("adopted", 0))):
            uses.append({"at": f"2026-10-{10 + i:02d}T10:00:00", "card": cid, "kind": "adopted", "session": f"bench:{cid}a{i}", "turn": str(i)})
        for i in range(int(c.get("again", 0))):
            uses.append({"at": f"2026-10-{20 + i:02d}T10:00:00", "card": cid, "kind": "again", "session": f"bench:{cid}g{i}", "turn": ""})
    path = vault / experience.USES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in uses), encoding="utf-8")
    return vault


def state24(vault: Path) -> tuple[list[dict], list[dict], dict, set[str]]:
    cards = experience.load_cards(vault)
    for c in cards:
        c["path"] = vault / c["rel"]
    used = experience.usage(vault)
    cand = skills.candidates(vault, cards, used, [])
    return cand["pool"], cand["singles"], used, cand["covered"]


def prompt24(s: dict) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        vault = build24(Path(tmp), s)
        pool, singles, used, _ = state24(vault)
        return skills.prompt(vault, pool, singles, [], used)[0]


def prepare24(args) -> None:
    cases = sorted(load("24", args.split), key=lambda s: opaque("24", s["id"]))
    rows = [{"id": opaque("24", s["id"]), "prompt": prompt24(s)} for s in cases]
    n = write_batches(rows, Path(args.out))
    chars = [len(r["prompt"]) for r in rows]
    print(json.dumps({"split": args.split, "cases": len(rows), "batches": n, "prompt_chars_mean": round(sum(chars) / len(chars))}))


JUDGE24 = """You are checking a "skill" (a step-by-step procedure) that an AI drafted from a person's experience cards.
Judge it only against the cards it rests on.

[Cards it rests on]
{cards}

[Skill]
name: {name}
when to use: {use_when}
steps:
{steps}

Answer two questions, each yes or no:
1. faithful: does every step say only what these cards' actions, results and lessons support (no step, tool,
   number or claim the cards do not have; a general rewording of a card's lesson is fine)?
2. subject_free: do the name and "when to use" read without any name, tool, product or noun specific to one card's
   subject, so they would apply unchanged to a task on another subject?
Reply with JSON only: {{"faithful": "yes"|"no", "subject_free": "yes"|"no", "why": "one short sentence"}}"""


def score24(args) -> None:
    cases = {opaque("24", s["id"]): s for s in load("24", args.split)}
    replies = read_replies(Path(args.replies))
    verdicts = read_replies(Path(args.verdicts)) if args.verdicts else {}
    tally = Counter()
    judge_rows = []
    rows = []
    for oid, s in sorted(cases.items()):
        if oid not in replies:
            tally["missing"] += 1
            continue
        with tempfile.TemporaryDirectory() as tmp:
            vault = build24(Path(tmp), s)
            pool, singles, used, covered = state24(vault)
            by_id = {c["id"]: c for c in pool}
            drafts, dropped = skills.parse(replies[oid], by_id, {c["id"] for c in singles}, covered)
            ids = card_ids(s)
            gold = [{ids[k] for k in g} for g in s.get("expect") or []]
            should = bool(gold)
            tally["should" if should else "should_not"] += 1
            tally["dropped_by_code"] += len(dropped)
            right = any(len(set(d["cards"]) & g) >= min(2, len(g)) and set(d["cards"]) <= g for d in drafts for g in gold)
            exact = any(set(d["cards"]) == g for d in drafts for g in gold)
            wrong_cards = sum(1 for d in drafts if not any(set(d["cards"]) <= g for g in gold))
            if should:
                tally["right"] += right
                tally["exact"] += exact
                tally["wrong_card_drafts"] += wrong_cards
            else:
                tally["drafted_when_not"] += bool(drafts)
            for j, d in enumerate(drafts):
                jid = f"{oid}-{j}"
                src = "\n".join(f"- [{c}] " + skills._card_line(by_id[c], used, "en").split("] ", 1)[1] for c in d["cards"])
                judge_rows.append({"id": jid, "prompt": JUDGE24.format(cards=src, name=d["name"], use_when=d["use_when"],
                                                                       steps="\n".join(f"{i}. {x}" for i, x in enumerate(d["steps"], 1)))})
                if should and right:
                    tally["drafts_on_should"] += 1
                    v = verdicts.get(jid)
                    if v:
                        vj = experience._json_array("[" + v + "]")
                        vj = vj[0] if vj and isinstance(vj[0], dict) else {}
                        tally["judged"] += 1
                        tally["faithful"] += str(vj.get("faithful", "")).lower() == "yes"
                        tally["subject_free"] += str(vj.get("subject_free", "")).lower() == "yes"
            rows.append({"id": oid, "kind": s["kind"], "drafts": len(drafts), "right": right, "dropped": dropped})
    if args.judge_out:
        n = write_batches(judge_rows, Path(args.judge_out), 40)
        tally["judge_batches"] = n
    print(json.dumps({"split": args.split, **tally}, ensure_ascii=False))
    if args.detail:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))


# ---------- 第 25 套：宿主取用 ----------

HOST25 = """【会话开始时，系统注入的上下文】
{digest}

【你可以调用的工具】
krouter_skill：{tool}

【用户消息】
{query}

【评测说明，不是用户说的】请像平时在这个会话里那样处理上面这条用户消息，不要真的去执行任何操作。如果你会先调用
krouter_skill，只输出一行 `CALL krouter_skill {{"id": "<编号>"}}`，别的什么都不写；不调用的话，就直接写回复的开头，最多五句话。"""
HOST25_2 = """{first}

【你调用了 krouter_skill，工具返回】
{text}

【评测说明，不是用户说的】现在写你给用户的回复：最多八句话，不要真的去执行任何操作。"""


def build25(root: Path, data: dict) -> Path:
    vault = root / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for card in sorted((REPO / "bench/transfer/cards").glob("*.md")):
        shutil.copy(card, folder / card.name)  # 第 13 套的 14 张卡：经验摘要照常在前
    sk = vault / skills.FOLDER
    sk.mkdir(parents=True, exist_ok=True)
    for s in data["skills"]:
        steps = "\n".join(f"{i}. {x}" for i, x in enumerate(s["steps"], 1))
        (sk / f"技能｜{s['name']}.md").write_text(
            f"---\ntitle: \"技能｜{s['name']}\"\ntype: {skills.TYPE}\nstatus: {s.get('status', 'active')}\n"
            f"skill_id: {s['id']}\nuse_when: \"{s['use_when']}\"\ncards: C01\ndrafted: 2026-10-01\n---\n\n"
            f"# 技能｜{s['name']}\n\n**什么时候用**：{s['use_when']}\n\n## 做法\n\n{steps}\n\n## 出处\n\n- 评测用，手写。\n",
            encoding="utf-8")
    return vault


def skills25() -> dict:
    return json.loads((HERE / "set25_skills.json").read_text(encoding="utf-8"))


def context25(vault: Path) -> tuple[str, str]:
    import mcp_server

    digest = experience.digest(vault) + "\n\n" + skills.digest(vault)
    return digest, mcp_server.skills_description(skills.listing(vault))


def prepare25(args) -> None:
    data = skills25()
    cases = sorted(load("25", args.split), key=lambda c: opaque("25", c["id"]))
    with tempfile.TemporaryDirectory() as tmp:
        vault = build25(Path(tmp), data)
        digest, tool = context25(vault)
    rows = [{"id": opaque("25", c["id"]), "prompt": HOST25.format(digest=digest, tool=tool, query=c["query"])} for c in cases]
    n = write_batches(rows, Path(args.out))
    print(json.dumps({"split": args.split, "cases": len(rows), "batches": n, "context_chars": len(digest) + len(tool),
                      "skills_part_chars": len(skills.digest(build25(Path(tempfile.mkdtemp()), data)))}))


CALL = re.compile(r"CALL\s+krouter_skill\s*(\{.*?\})", re.S)
SKILL_ID = re.compile(r"(?<![A-Za-z0-9])(S[0-9a-f]{4})(?![A-Za-z0-9])")
CARD_ID = re.compile(r"(?<![A-Za-z0-9])(C\d{2})(?!\d)")


def called(reply: str) -> str:
    m = CALL.search(reply or "")
    if not m:
        return ""
    try:
        return str(json.loads(m.group(1)).get("id") or "").strip()
    except ValueError:
        return ""


def phase2(args) -> None:
    data = skills25()
    cases = {opaque("25", c["id"]): c for c in load("25", args.split)}
    first = read_replies(Path(args.calls))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        vault = build25(Path(tmp), data)
        digest, tool = context25(vault)
        for oid, c in sorted(cases.items()):
            sid = called(first.get(oid, ""))
            if not sid:
                continue
            text = skills.show(vault, sid) or f"no skill {sid!r}"
            p1 = HOST25.format(digest=digest, tool=tool, query=c["query"]).rsplit("【评测说明", 1)[0].rstrip()
            rows.append({"id": oid, "prompt": HOST25_2.format(first=p1, text=text)})
    n = write_batches(rows, Path(args.out))
    print(json.dumps({"split": args.split, "phase2_prompts": len(rows), "batches": n}))


JUDGE25 = """A user asked an AI assistant for help, and the assistant fetched a procedure (a "skill") and replied.
Judge only whether the reply follows the skill.

[User message]
{query}

[Skill the assistant fetched]
{skill}

[Assistant's reply]
{reply}

Question: does the reply follow the skill's steps for this task (it applies them, in substance and roughly in order,
to what the user asked; it does not ignore them or do something else instead)? Reply with JSON only:
{{"follows": "yes"|"no", "why": "one short sentence"}}"""


def score25(args) -> None:
    data = skills25()
    cases = {opaque("25", c["id"]): c for c in load("25", args.split)}
    first = read_replies(Path(args.calls))
    second = read_replies(Path(args.replies)) if args.replies else {}
    verdicts = read_replies(Path(args.verdicts)) if args.verdicts else {}
    t = Counter()
    judge_rows = []
    with tempfile.TemporaryDirectory() as tmp:
        vault = build25(Path(tmp), data)
        for oid, c in sorted(cases.items()):
            if oid not in first:
                t["missing"] += 1
                continue
            sid = called(first[oid])
            reply = second.get(oid, "") if sid else first[oid]
            cited = set(SKILL_ID.findall(reply)) | ({sid} if sid else set())
            if c.get("expect"):
                t["applicable"] += 1
                if sid == c["expect"]:
                    t["fetched_right"] += 1
                    judge_rows.append({"id": oid, "prompt": JUDGE25.format(query=c["query"], skill=skills.show(vault, sid),
                                                                           reply=reply)})
                    v = verdicts.get(oid)
                    if v:
                        vj = experience._json_array("[" + v + "]")
                        vj = vj[0] if vj and isinstance(vj[0], dict) else {}
                        t["judged"] += 1
                        t["followed"] += str(vj.get("follows", "")).lower() == "yes"
                elif sid:
                    t["fetched_wrong"] += 1
                else:
                    t["not_fetched"] += 1
            else:
                t["quiet"] += 1
                t["quiet_with_skill"] += bool(cited)
                t["quiet_cards_cited"] += bool(CARD_ID.search(reply))
    if args.judge_out:
        t["judge_batches"] = write_batches(judge_rows, Path(args.judge_out), 40)
    print(json.dumps({"split": args.split, **t}, ensure_ascii=False))


# ---------- 第 26 套：采纳判定与门槛 ----------

def score26(args) -> None:
    items = load("26", args.split)
    t = Counter()
    for it in items:
        sid = "S0a1b"
        turns = [{"ts": "2026-11-01T10:00:00", "ask": it["ask"], "answer": it["reply"].replace("{id}", sid)},
                 {"ts": "2026-11-01T10:05:00", "ask": it["next"], "answer": "好。" if it.get("lang", "zh") == "zh" else "OK."}]
        ev = experience.uses_in(turns, {sid})
        adopted = any(e["kind"] == "adopted" for e in ev)
        offered = any(e["kind"] == "offered" for e in ev)
        t[f"{it['kind']}_n"] += 1
        t[f"{it['kind']}_adopted"] += adopted
        t["offered_recorded"] += offered
    pos = t["adopt_n"]
    neg = sum(v for k, v in t.items() if k.endswith("_n")) - pos
    fa = sum(v for k, v in t.items() if k.endswith("_adopted")) - t["adopt_adopted"]
    out = {"split": args.split, **t, "p_true": round(t["adopt_adopted"] / pos, 3) if pos else None,
           "p_false": round(fa / neg, 3) if neg else None}
    print(json.dumps(out, ensure_ascii=False))


def binom_ge(n: int, p: float, k: int) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def thresholds(args) -> None:
    """The registered rule: the smallest withdrawal count W in {4, 5, 6, 8, 10}, then the smallest promotion count k in
    {1, 2, 3}, such that a draft that never fits is promoted before withdrawal with probability ≤ 5% (false adoptions
    at the observed rate, W offers) and one that always fits is promoted within W offers with probability ≥ 90%."""
    pf, pt = max(args.p_false, 0.02), args.p_true  # 开发集上一次误判都没有时，按 2% 算，不当成 0
    rows = []
    for w in (4, 5, 6, 8, 10):
        for k in (1, 2, 3):
            bad, good = binom_ge(w, pf, k), binom_ge(w, pt, k)
            rows.append({"W": w, "k": k, "useless_promoted": round(bad, 4), "useful_promoted": round(good, 4),
                         "ok": bad <= 0.05 and good >= 0.90})
    pick = next((r for r in rows if r["ok"]), None)
    print(json.dumps({"p_true": pt, "p_false_used": pf, "pick": pick, "grid": rows}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("split")
    sp.add_argument("--set", required=True)
    sp.add_argument("--raw", required=True)
    for name in ("prepare24", "prepare25"):
        p = sub.add_parser(name)
        p.add_argument("split")
        p.add_argument("--out", required=True)
    p = sub.add_parser("score24")
    p.add_argument("split")
    p.add_argument("--replies", required=True)
    p.add_argument("--judge-out", default="")
    p.add_argument("--verdicts", default="")
    p.add_argument("--detail", action="store_true")
    p = sub.add_parser("phase2")
    p.add_argument("split")
    p.add_argument("--calls", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("score25")
    p.add_argument("split")
    p.add_argument("--calls", required=True)
    p.add_argument("--replies", default="")
    p.add_argument("--judge-out", default="")
    p.add_argument("--verdicts", default="")
    p = sub.add_parser("score26")
    p.add_argument("split")
    p = sub.add_parser("thresholds")
    p.add_argument("--p-true", type=float, required=True)
    p.add_argument("--p-false", type=float, required=True)
    args = ap.parse_args()
    {"split": split, "prepare24": prepare24, "score24": score24, "prepare25": prepare25, "phase2": phase2,
     "score25": score25, "score26": score26, "thresholds": thresholds}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
