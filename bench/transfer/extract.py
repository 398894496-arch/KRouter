#!/usr/bin/env python3
"""Set 17 (bench/memory_honesty/HELDOUT.md): when the host agent writes experience cards itself, are they any good?

The zero-key path: no model lane, the agent that ran the session records the lesson with `krouter_learn` (MCP) or
`experience.py learn`. Twelve synthetic sessions (`set17_sessions.jsonl`, written for this check, never a real one):
7 with a lesson, 3 whose lesson is already a card in the vault, 2 with none. Each prompt gives the host what it would
have at the end of such a session: the session-start digest, the session, and `experience.LEARN_HELP` (the tool's own
description); the host says with what arguments it would call `krouter_learn`. Every proposed card then goes through
`experience.learn()` on a fresh copy of the vault, exactly as the tool would, and is scored mechanically against the
session's gold: subject words absent from title, lesson and `when` (subject-free); the action and result holding a
gold term (faithful); nothing written for a duplicate or a session with no lesson.

    python3 bench/transfer/extract.py prepare --out DIR
    (DIR/batch_01.jsonl {id, prompt} answered into DIR/replies_<host>/batch_01.jsonl {id, response})
    python3 bench/transfer/extract.py score --replies DIR/replies_<host>

Set 19 (`--set 19`, `set19_sessions.jsonl`: 16 longer sessions written by another model, with drift and changes of
course) scores faithfulness and subject-freedom by a judge model that did not write the card: `score --set 19
--judge-out J` writes one judge prompt per written card, a subagent on the *other* host model answers them, and
`judged --set 19 --replies R --verdicts V` adds the verdicts. Cards no longer carry `when` phrases.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
import experience  # noqa: E402

VAULTS = {"zh": ("template-zh", "cards"), "en": ("template", "cards_en")}
PROMPT = {
    "zh": """【会话开始时，系统注入的上下文】
{digest}

【这段会话】
{session}

【工具 krouter_learn 的说明】
{help}

【评测说明，不是用户说的】这段会话现在要结束了。如果你会调用 krouter_learn，把每次调用的参数（工具说明里列的那些字段）写成一个
JSON 数组，0 到 2 个对象；不会调用就写 []。只输出这个 JSON 数组。""",
    "en": """[Context the system injected at session start]
{digest}

[This session]
{session}

[Description of the tool krouter_learn]
{help}

[Bench note, not from the user] This session is about to end. If you would call krouter_learn, write the arguments of
each call (the fields the tool description lists) as one JSON array of 0 to 2 objects; if you would not call it,
write []. Output only that JSON array.""",
}


SET = "17"
JUDGE = """You are checking an experience card that an AI assistant wrote from a session. Judge it only against the session.

[Session]
{session}

[Card]
situation: {situation}
action: {action}
result: {result}
lesson: {lesson}
title: {title}

Answer two questions, each yes or no:
1. faithful: do situation, action and result say only what the session shows (nothing invented, nothing that the
   session contradicts or abandoned along the way)?
2. subject_free: do the lesson and the title read without any name, tool, product or noun specific to this session's
   subject, so that they would apply unchanged to a task on another subject?
Reply with JSON only: {{"faithful": "yes"|"no", "subject_free": "yes"|"no", "why": "one short sentence"}}"""


def load() -> list[dict]:
    return [json.loads(x) for x in (HERE / f"set{SET}_sessions.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]


def build_vault(root: Path, lang: str) -> Path:
    template, cards = VAULTS[lang]
    vault = root / "vault"
    shutil.copytree(REPO / template, vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for card in sorted((HERE / cards).glob("*.md")):
        shutil.copy(card, folder / card.name)
    return vault


def transcript(s: dict) -> str:
    who = ("用户", "agent") if s["lang"] == "zh" else ("User", "Agent")
    return "\n".join(f"{who[0]}：{t['ask']}\n{who[1]}：{t['answer']}" if s["lang"] == "zh"
                     else f"{who[0]}: {t['ask']}\n{who[1]}: {t['answer']}" for t in s["turns"])


def prepare(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in load():
        with tempfile.TemporaryDirectory() as tmp:
            digest = experience.digest(build_vault(Path(tmp), s["lang"]))
        rows.append({"id": s["id"], "prompt": PROMPT[s["lang"]].format(digest=digest, session=transcript(s),
                                                                        help=experience.LEARN_HELP)})
    (out / "batch_01.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"sessions": len(rows), "batches": 1}))


def proposed(reply: str) -> list:
    m = re.search(r"\[.*\]", reply or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


RETRY = {"zh": "\n\n【工具 krouter_learn 返回】{why}\n\n【评测说明，不是用户说的】按工具返回的原因改写这次调用，把改好的参数写成同样的 JSON 数组（不再调用就写 []）。只输出这个 JSON 数组。",
         "en": "\n\n[Tool krouter_learn returned] {why}\n\n[Bench note, not from the user] Rewrite this call for the reason the tool gave and write the corrected arguments as the same JSON array ([] if you would not call it again). Output only that JSON array."}


def score_one(s: dict, reply: str, retry: str | None = None) -> dict:
    """One session's proposed cards through experience.learn(). As the MCP tool returns its reason to the agent, a
    refused call may be retried once: `retry` is the host's answer to that reason, used in place of the refused call."""
    items = proposed(reply)
    written, refused, retried, linked = [], [], False, []
    with tempfile.TemporaryDirectory() as tmp:
        vault = build_vault(Path(tmp), s["lang"])
        queue = list(items[:2])
        while queue:
            item = queue.pop(0)
            path, why = experience.learn(vault, item, "[[set17]]", writer="bench")
            if not path and why.startswith("again: "):
                linked.append(why[7:])  # 宿主判定摘要里已有：给旧卡记一次「又遇到」，不写新卡
                continue
            if not path and retry is not None and not retried:
                retried = True
                queue = proposed(retry)[:1] + queue
                continue
            if path:
                card = next(c for c in experience.load_cards(vault) if c["rel"].endswith(path.name))
                text = " ".join([card["title"], card["lesson"], " ".join(card["when"])])
                written.append({"subject_free": not has_any(text, s["subject"]),
                                "faithful": has_any(str(item.get("action", "")), s.get("action_any", []))
                                and has_any(str(item.get("result", "")), s.get("result_any", [])),
                                "card": {k: str(item.get(k) or "") for k in ("situation", "action", "result", "lesson")}
                                | {"title": card["title"]}})
            else:
                refused.append(why[:60])
    return {"id": s["id"], "kind": s["kind"], "proposed": len(items), "written": written, "refused": refused,
            "retried": retried, "linked": linked}


def first_refusal(s: dict, reply: str) -> str:
    """The reason experience.learn() gives for the first proposed card it refuses, or ""."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = build_vault(Path(tmp), s["lang"])
        for item in proposed(reply)[:2]:
            path, why = experience.learn(vault, item, "[[x]]", writer="bench")
            if not path and not why.startswith("again: "):
                return why
    return ""


def read_replies(folder: str) -> dict[str, str]:
    out = {}
    for f in sorted(Path(folder).glob("*.jsonl")) if folder and Path(folder).is_dir() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[str(r["id"])] = str(r.get("response") or "")
    return out


def retry_prompts(args) -> None:
    """Prompts for the calls experience.learn() refused: the first prompt, the host's call, and the tool's reason."""
    replies = read_replies(args.replies)
    first = {r["id"]: r["prompt"] for r in (json.loads(x) for x in Path(args.prompts).read_text(encoding="utf-8").splitlines() if x.strip())}
    rows = []
    for s in load():
        why = first_refusal(s, replies.get(s["id"], ""))
        if why:
            rows.append({"id": s["id"], "prompt": first[s["id"]] + "\n\n" + replies[s["id"]].strip() + RETRY[s["lang"]].format(why=why)})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch_01.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"retry_prompts": len(rows)}))


def score(args) -> None:
    replies = {}
    for f in sorted(Path(args.replies).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                replies[str(r["id"])] = str(r.get("response") or "")
    retries = read_replies(getattr(args, "retries", ""))
    rows = [score_one(s, replies.get(s["id"], ""), retries.get(s["id"])) for s in load()]
    cards = [w for r in rows for w in r["written"]]
    by = {k: [r for r in rows if r["kind"] == k] for k in ("lesson", "duplicate", "none")}
    res = {"lesson_sessions_with_a_card": sum(1 for r in by["lesson"] if r["written"]),
           "lesson_sessions": len(by["lesson"]),
           "cards_written": len(cards),
           "subject_free": sum(w["subject_free"] for w in cards), "faithful": sum(w["faithful"] for w in cards),
           "duplicates_proposed": sum(1 for r in by["duplicate"] if r["proposed"]),
           "duplicates_written": sum(1 for r in by["duplicate"] if r["written"]),
           "duplicate_sessions": len(by["duplicate"]),
           "none_written": sum(1 for r in by["none"] if r["written"]), "none_sessions": len(by["none"]),
           "refused_by_checks": sum(len(r["refused"]) for r in rows), "retried": sum(r["retried"] for r in rows),
           "missing_replies": sum(1 for s in load()
                                                                                          if s["id"] not in replies)}
    if SET != "17":
        res.pop("faithful")  # 第 19 套：忠于原会话由判分模型定（judged），这里只给机械的去题材数
        res["subject_free_mechanical"] = res.pop("subject_free")
    print(json.dumps(res, ensure_ascii=False))
    if args.rows:
        for r in rows:
            print(json.dumps({**r, "written": [{k: v for k, v in w.items() if k != "card"} for w in r["written"]]},
                             ensure_ascii=False))
    if getattr(args, "judge_out", ""):
        sessions = {x["id"]: x for x in load()}
        out = Path(args.judge_out)
        out.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"id": f"{r['id']}#{n}", "prompt": JUDGE.format(session=transcript(sessions[r["id"]]),
                                                                           **w["card"])}, ensure_ascii=False)
                 for r in rows for n, w in enumerate(r["written"])]
        (out / "batch_01.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"judge_prompts": len(lines)}))


REVIEW = """A test writer labelled the session below as a *duplicate*: its lesson is meant to be the same as a lesson
already stored, though the subject differs. Check the label, reading only the session and the two texts below.

[Session]
{session}

[Stored lesson]
{lesson}

[The writer's reason]
{reason}

Is the lesson this session teaches the same as the stored lesson (the same situation and the same way out, whatever
the subject)? Reply with JSON only: {{"same": "yes"|"no"|"unclear", "why": "one short sentence"}}"""


def read_review(folder: str) -> set[str] | None:
    """Session ids whose duplicate label the reviewer confirmed ("yes"); None when there is no review."""
    if not folder:
        return None
    out = set()
    for sid, text in read_replies(folder).items():
        m = re.search(r"\{.*\}", text, re.S)
        try:
            if m and str(json.loads(m.group(0)).get("same", "")).lower().startswith("y"):
                out.add(sid)
        except ValueError:
            pass
    return out


def review_prompts(args) -> None:
    """One prompt per duplicate session, for a model other than the writer to confirm the label."""
    lessons = {}
    for folder in ("cards", "cards_en"):
        for p in sorted((HERE / folder).glob("*.md")):
            meta, body = experience.ri.split_frontmatter(p.read_text(encoding="utf-8"))
            m = re.search(r"- (?:通用说法|Lesson)[:：]\s*(.+)", body)
            lessons[(meta.get("card_id"), "zh" if folder == "cards" else "en")] = m.group(1).strip() if m else ""
    rows = [{"id": s["id"], "prompt": REVIEW.format(session=transcript(s), lesson=lessons.get((s["dup_of"], s["lang"]), ""),
                                                   reason=s.get("dup_reason") or "")}
            for s in load() if s["kind"] == "duplicate"]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch_01.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps({"review_prompts": len(rows)}))


def judged(args) -> None:
    """Set 19's registered score: lesson sessions with a card, and the judge's faithful / subject-free verdicts."""
    replies, verdicts = {}, {}
    for f in sorted(Path(args.replies).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                replies[str(r["id"])] = str(r.get("response") or "")
    for f in sorted(Path(args.verdicts).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                m = re.search(r"\{.*\}", str(r.get("response") or ""), re.S)
                try:
                    verdicts[str(r["id"])] = json.loads(m.group(0)) if m else {}
                except ValueError:
                    verdicts[str(r["id"])] = {}
    retries = read_replies(getattr(args, "retries", ""))
    rows = [score_one(s, replies.get(s["id"], ""), retries.get(s["id"])) for s in load()]
    ids = [f"{r['id']}#{n}" for r in rows if r["kind"] == "lesson" for n in range(len(r["written"]))]
    yes = lambda i, k: str(verdicts.get(i, {}).get(k, "")).lower().startswith("y")  # noqa: E731
    by = {k: [r for r in rows if r["kind"] == k] for k in ("lesson", "duplicate", "none")}
    agreed = read_review(getattr(args, "review", ""))
    if agreed is not None:
        disputed = [r["id"] for r in by["duplicate"] if r["id"] not in agreed]
        by["duplicate"] = [r for r in by["duplicate"] if r["id"] in agreed]
    else:
        disputed = []
    dups = {x["id"]: x.get("dup_of") for x in load()}
    print(json.dumps({"lesson_sessions_with_a_card": sum(1 for r in by["lesson"] if r["written"]),
                      "duplicates_linked_right": sum(1 for r in by["duplicate"] if dups.get(r["id"]) in r.get("linked", [])),
                      "duplicates_disputed_left_out": disputed,
                      "lesson_sessions": len(by["lesson"]), "cards_on_lesson_sessions": len(ids),
                      "retried": sum(r["retried"] for r in rows),
                      "faithful": sum(yes(i, "faithful") for i in ids), "subject_free": sum(yes(i, "subject_free") for i in ids),
                      "unjudged": sum(1 for i in ids if i not in verdicts),
                      "duplicates_written": sum(1 for r in by["duplicate"] if r["written"]),
                      "duplicate_sessions": len(by["duplicate"]),
                      "none_written": sum(1 for r in by["none"] if r["written"]), "none_sessions": len(by["none"])},
                     ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("--replies", required=True)
    s.add_argument("--rows", action="store_true")
    s.add_argument("--judge-out", default="", help="set 19: write the judge prompts for the cards written here")
    s.add_argument("--retries", default="", help="the hosts' answers to the refusals (`retry`)")
    j = sub.add_parser("judged")
    j.add_argument("--replies", required=True)
    j.add_argument("--verdicts", required=True)
    j.add_argument("--retries", default="")
    j.add_argument("--review", default="", help="set 23: the reviewer's answers on the duplicate labels")
    v = sub.add_parser("review", help="set 23: prompts asking another model to confirm each duplicate label")
    v.add_argument("--out", required=True)
    r = sub.add_parser("retry", help="prompts for refused calls, with the tool's reason, for one retry")
    r.add_argument("--replies", required=True)
    r.add_argument("--prompts", required=True, help="the batch file the replies answered")
    r.add_argument("--out", required=True)
    for sp in (p, s, j, r, v):
        sp.add_argument("--set", default="17", choices=("17", "19", "20", "21", "23"))
    args = ap.parse_args()
    global SET
    SET = args.set
    {"prepare": prepare, "score": score, "judged": judged, "retry": retry_prompts, "review": review_prompts}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
