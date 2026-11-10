#!/usr/bin/env python3
"""Skills: experience that keeps coming back grows into a procedure the host agent can follow.

An experience card (`experience.py`) says "in situation S, doing D gave R". When one card's lesson is borne out again
and again (adopted, or seen again in another session), or when several cards describe the same kind of situation, the
nightly run drafts a **skill**: one Markdown page with a name, one sentence on when to use it, numbered steps, and
where it came from (which cards, which sessions). Pages live in the memory folder, `02 经验与方法/技能/`:

    ---
    title: "技能｜…"
    type: krouter-skill
    status: draft            (draft → active, or draft → retired)
    skill_id: S1a2b
    use_when: "…"
    cards: C05; E1a2b
    drafted: 2026-11-10
    ---
    # 技能｜…
    **什么时候用**：…
    ## 做法
    1. … 2. …
    ## 出处
    - 经验卡〔C05〕[[…]]：采纳 2 次、又遇到 1 次 …

**Drafting** needs a model and goes through the host lane (`llm.complete`: a key the user set, or the agent's own
logged-in CLI). One call a night at most, and only when the cards that could grow into a skill changed since the last
attempt (the signature is kept in the state directory). The model may draft from a card that has been borne out
DRAFT_EVIDENCE times (adopted + seen again), or from two or more cards it judges to be the same kind of situation; the
code checks every draft (the cards exist and are not already in a skill, a single card has the evidence, every number
is in the cards, no key-shaped text, the steps share words with the cards). No model lane: drafting is skipped quietly
and the nightly report says so.

**Taking effect without anyone approving.** A draft is shown in the session-start digest as a suggestion, apart from
the facts and marked as a draft. The host cites a skill's id when it uses one, and the use records
(`experience.record_uses`, at session import, no model) count `offered` and `adopted` for skill ids as for cards. A
draft adopted PROMOTE_ADOPTED times becomes `active`; a draft nobody adopted for WITHDRAW_DAYS days, or offered
WITHDRAW_OFFERED times and never adopted, or whose cards are all gone, is `retired`; a draft offered SINK_OFFERED times
and never adopted sinks to the bottom of the list. Every draft, promotion and withdrawal is its own git commit with a
readable message and a ledger entry; `skills.py undo <run>` (or `import_sessions.py --undo <run>`) reverts one.

**Reaching the host.** Nothing is written into any agent's configuration. The session-start digest lists each skill's
name and when to use it; the host fetches the full text with the MCP tool `krouter_skill` (or reads the page, whose
path the digest gives). `skills.py export` writes them in an app's own skill format, only when asked.

**Switch.** `KROUTER_SKILLS=0` turns skills off, `=1` on; otherwise DEFAULT_ON. `KROUTER_EXPERIENCE=0` turns them
off too. Measured: sets 24–26 in `bench/memory_honesty/HELDOUT.md`; numbers in `docs/SKILLS.md`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experience  # noqa: E402
import recall_index as ri  # noqa: E402
import zones  # noqa: E402
from krouter_redact import redact  # noqa: E402

FOLDER = ri.SKILLS_DIR  # 02 经验与方法/技能
TYPE = "krouter-skill"
DEFAULT_ON = False  # 第 24、25 套过线后再打开；见 docs/SKILLS.md

# 门槛（转正、撤回在第 26 套开发部分上定，见 bench/skills/README.md）
DRAFT_EVIDENCE = 3    # 一张卡被采纳 + 又遇到合计这么多次，就可以单独长成技能
GROUP_MIN = 2         # 几张卡说的是同一类处境：至少这么多张
PROMOTE_ADOPTED = 2   # 第 26 套开发部分定；草稿被采纳这么多次：转正
WITHDRAW_DAYS = 45    # 草稿起草这么多天一次没被采纳：撤回
WITHDRAW_OFFERED = 4  # 第 26 套开发部分按登记的规则定（W=4, k=2）；草稿被提出这么多次一次没被采纳：撤回
SINK_OFFERED = 2      # W 的一半；草稿被提出这么多次一次没被采纳：排到最后
MAX_DRAFTS = 3        # 一晚最多起草这么多份
LIST_ACTIVE = 15      # 摘要里最多列这么多个转正的技能
LIST_DRAFTS = 5       # 和这么多份草稿


def on() -> bool:
    """Skills in the digest, the `krouter_skill` tool and the nightly step: `KROUTER_SKILLS=1` on, `=0` off, else
    DEFAULT_ON; always off when the experience cards are (`KROUTER_EXPERIENCE=0`)."""
    if not experience.digest_on():
        return False
    flag = os.environ.get("KROUTER_SKILLS", "").strip().lower()
    if flag in ("0", "off", "false", "no"):
        return False
    return flag in ("1", "on", "true", "yes") or DEFAULT_ON


# ---------- 读技能页 ----------

STEP_RE = re.compile(r"^\s*(\d+)[.、)]\s*(.+)$")
HEAD_STEPS = ("## 做法", "## Steps")
HEAD_SOURCES = ("## 出处", "## Sources")
WHEN_LINE = re.compile(r"^\*\*(?:什么时候用|When to use)\*\*\s*[:：]\s*(.+)$", re.M)


def _section(body: str, heads: tuple[str, ...]) -> str:
    for head in heads:
        m = re.search(rf"(?m)^{re.escape(head)}\s*$\n(.*?)(?=^## |\Z)", body, re.S)
        if m:
            return m.group(1)
    return ""


def load(vault: Path, include_retired: bool = False) -> list[dict]:
    """Every skill page: [{id, rel, name, use_when, steps, cards, status, drafted, promoted, lang}]."""
    folder = vault / ri.skills_rel(vault)
    if not folder.is_dir():
        return []
    out = []
    for page in sorted(folder.glob("*.md")):
        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = ri.split_frontmatter(text)
        if meta.get("type") != TYPE:
            continue
        status = (meta.get("status") or "draft").lower()
        if status in ri.DEAD_STATUS and not include_retired:
            continue
        steps = [m.group(2).strip() for ln in _section(body, HEAD_STEPS).splitlines() if (m := STEP_RE.match(ln))]
        when = meta.get("use_when") or ((m := WHEN_LINE.search(body)) and m.group(1).strip()) or ""
        name = (meta.get("title") or page.stem)
        for p in ("技能｜", "Skill: "):
            name = name.removeprefix(p)
        out.append({
            "id": meta.get("skill_id") or "S" + hashlib.sha1(page.name.encode("utf-8")).hexdigest()[:4],
            "rel": str(page.relative_to(vault)).replace(os.sep, "/"),
            "path": page,
            "name": name,
            "use_when": when,
            "steps": steps,
            "cards": [c.strip() for c in re.split(r"[;；,，\s]+", meta.get("cards") or "") if c.strip()],
            "status": status if status in ("draft", "active") or status in ri.DEAD_STATUS else "draft",
            "drafted": meta.get("drafted") or meta.get("date") or "",
            "promoted": meta.get("promoted") or "",
            "lang": "zh" if ri.CJK_RE.search(name + when) else "en",
        })
    return out


def ids(vault: Path) -> set[str]:
    """Ids of the live skills (drafts and active): the use records count them as they count cards."""
    try:
        return {s["id"] for s in load(vault)} if on() else set()
    except Exception:  # noqa: BLE001
        return set()


def find(vault: Path, sid: str) -> dict | None:
    sid = sid.strip().strip("〔〕[]（）()")
    return next((s for s in load(vault, include_retired=True) if s["id"].lower() == sid.lower()), None)


# ---------- 证据：每张卡被采纳、又遇到了几次 ----------

def evidence(used: dict, cid: str) -> int:
    u = used.get(cid, {})
    return int(u.get("adopted", 0)) + int(u.get("again", 0))


def sessions_of(vault: Path, cids: set[str]) -> list[str]:
    """Sessions in the use records where these cards were adopted or came up again (newest last), each once."""
    path = zones.path(vault, experience.USES)
    out: list[str] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("card") in cids and d.get("kind") in ("adopted", "again") and d.get("session"):
            s = str(d["session"])
            if s not in out:
                out.append(s)
    return out


def candidates(vault: Path, cards: list[dict] | None = None, used: dict | None = None,
               skills: list[dict] | None = None) -> dict:
    """{pool: cards not yet in a live skill, singles: those of them borne out DRAFT_EVIDENCE times}."""
    cards = experience.load_cards(vault) if cards is None else cards
    used = experience.usage(vault) if used is None else used
    skills = load(vault) if skills is None else skills
    covered = {c for s in skills for c in s["cards"]}
    pool = [c for c in cards if c["id"] not in covered]
    singles = [c for c in pool if evidence(used, c["id"]) >= DRAFT_EVIDENCE]
    return {"pool": pool, "singles": singles, "covered": covered}


# ---------- 起草（走宿主通道的模型） ----------

PROMPT = """下面是一个人攒下的经验卡（每张是别的任务里学到的一条经验，带编号和被证实的次数），以及已经有的技能。

只做一件事：把值得长成「技能」的经验起草出来。技能 = 遇到某一类处境时，可以照着一步一步做的做法。
只有两种情况可以起草：
1. 「被反复证实的卡」里列出的卡，可以单独长成一个技能；
2. 两张或更多张卡说的是**同一类处境**：题材不同，但遇到的是同一类问题、管用的是同一类办法，合成一个技能。
   只是用了同一个词、同一个题材或同一个工具，处境却不一样的，不算；两条通用说法只是都很笼统地沾边（都是「慢慢来」
   「先留一手」「先问清楚」）也不算：要遇到的问题是一类，要做的那一步也是同一步，才合；拿不准就不要合。
已有技能用到的卡不要再用。没有值得起草的，就回 []。

每个技能一个 JSON 对象：
- "cards"：依据的卡号列表，例 ["C05", "E1a2b"]
- "name"：技能名，6–20 字
- "use_when"：一句话说什么时候用，写成「当……时」
- name 和 use_when 从卡的「通用说法」概括，不从「处境」里取词：不出现题材、工具、行当、东西的名字，专门的词换成一般的说法
  （「合并数据」→「把几份东西合到一起」，「恢复训练」→「停了一阵再接着做一件费力的事」，「转机」→「两段安排之间」）。
  自测：这句话原样讲给修 bug 的人、写报告的人、做饭的人都说得通吗？只适合这一类事，就再往上概括一层
- "steps"：1–6 步，每步一句话，能照着做；每一步都要在这些卡的做法、结果或通用说法里找得到，不加卡里没有的步骤、检查、
  工具或数字，卡里只有一步就只写一步，不要为了凑步数补；也用一般的说法，让换了题材的人照样能做
用中文写（卡片的语言）。不写密钥、人名和私人信息。只输出 JSON 数组。

被反复证实的卡（可以单独起草）：{singles}

经验卡：
{cards}

已有技能：
{skills}
"""
PROMPT_EN = """Below are a person's experience cards (each a lesson learned on some other task, with its id and how often it
was borne out), and the skills that already exist.

Do one thing: draft the lessons worth growing into a "skill". A skill is a procedure to follow step by step whenever
a certain kind of situation comes up. Draft only in two cases:
1. a card listed under "cards borne out repeatedly" may become a skill on its own;
2. two or more cards describe **the same kind of situation**: different subjects, but the same kind of problem and
   the same kind of way out; merge them into one skill. Sharing a word, a subject or a tool while the situation
   differs does not count; nor do two lessons that only share some broad advice ("go gradually", "keep a fallback",
   "ask first"): the problem must be of one kind and the step to take the same step. When unsure, do not merge.
Do not use a card an existing skill already uses. If nothing is worth drafting, reply [].

Each skill is a JSON object:
- "cards": the ids it rests on, e.g. ["C05", "E1a2b"]
- "name": the skill's name, 3–8 words
- "use_when": one sentence on when to use it, "When …"
- take name and use_when from the cards' lessons, not their situations: no subject, tool, trade or object named,
  each specific term replaced by a general word ("merging data" → "putting several pieces together", "a flight
  connection" → "the gap between two parts of a plan"). Test it: would it make sense word for word to someone fixing a
  bug, writing a report and cooking? If it only fits this kind of thing, say it one level higher
- "steps": 1–6 steps, one sentence each, that can be followed; each step must be found in these cards' actions,
  results or lessons: no step, check, tool or number the cards do not have, and if the cards give one step, write one
  step, do not pad; in general words too, so someone on another subject can follow them
Write in English, the cards' language. No keys, names or private details. Output only the JSON array.

Cards borne out repeatedly (may be drafted alone): {singles}

Experience cards:
{cards}

Existing skills:
{skills}
"""


def _card_line(c: dict, used: dict, lang: str) -> str:
    u = used.get(c["id"], {})
    page = experience._fields(_body(c))
    if lang == "zh":
        bits = [f"处境：{page.get('处境', '')}", f"做法：{page.get('做法', '')}", f"结果：{page.get('结果', '')}",
                f"通用说法：{c['lesson']}", f"被采纳 {u.get('adopted', 0)} 次、又遇到 {u.get('again', 0)} 次"]
        return f"〔{c['id']}〕" + "；".join(bits)
    bits = [f"situation: {page.get('处境', '')}", f"action: {page.get('做法', '')}", f"result: {page.get('结果', '')}",
            f"lesson: {c['lesson']}", f"adopted {u.get('adopted', 0)}, seen again {u.get('again', 0)}"]
    return f"[{c['id']}] " + "; ".join(bits)


_BODIES: dict[str, str] = {}


def _body(card: dict) -> str:
    """The card page's body (fields), cached per path for one run."""
    key = str(card.get("path") or card["rel"])
    if key not in _BODIES:
        try:
            _BODIES[key] = ri.split_frontmatter(Path(card["path"]).read_text(encoding="utf-8"))[1]
        except (OSError, KeyError):
            _BODIES[key] = ""
    return _BODIES[key]


def prompt(vault: Path, pool: list[dict], singles: list[dict], skills: list[dict], used: dict) -> tuple[str, str]:
    """(prompt, lang) for one drafting call."""
    lang = experience.lang_of(pool) if pool else "zh"
    for c in pool:
        c.setdefault("path", vault / c["rel"])
    none = "（无）" if lang == "zh" else "(none)"
    sk = "\n".join((f"〔{s['id']}〕{s['name']}：{s['use_when']}（用到 {'、'.join(s['cards'])}）" if lang == "zh"
                    else f"[{s['id']}] {s['name']}: {s['use_when']} (uses {', '.join(s['cards'])})") for s in skills)
    template = PROMPT if lang == "zh" else PROMPT_EN
    text = template.format(singles=("、" if lang == "zh" else ", ").join(c["id"] for c in singles) or none,
                           cards="\n".join(_card_line(c, used, lang) for c in pool) or none, skills=sk or none)
    return redact(text), lang


def _source_text(cards: list[dict]) -> str:
    return "\n".join(_body(c) + "\n" + c["lesson"] for c in cards)


def check(item, by_id: dict[str, dict], singles: set[str], covered: set[str]) -> tuple[dict | None, str]:
    """(draft, "") when one proposed skill holds up, else (None, why). No model."""
    import answer_cards

    if not isinstance(item, dict):
        return None, "not an object"
    raw_cards = item.get("cards") if isinstance(item.get("cards"), list) else []
    cids = list(dict.fromkeys(str(c).strip().strip("〔〕[]") for c in raw_cards if str(c).strip()))
    if not cids:
        return None, "no cards"
    if any(c not in by_id for c in cids):
        return None, f"unknown card {next(c for c in cids if c not in by_id)}"
    if any(c in covered for c in cids):
        return None, f"card {next(c for c in cids if c in covered)} is already in a skill"
    if len(cids) < GROUP_MIN and cids[0] not in singles:
        return None, f"one card ({cids[0]}) that has not been borne out {DRAFT_EVIDENCE} times"
    name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip().strip("「」\"")
    when = re.sub(r"\s+", " ", str(item.get("use_when") or "")).strip()
    steps = item.get("steps") if isinstance(item.get("steps"), list) else []
    steps = [re.sub(r"^\s*\d+[.、)]\s*", "", re.sub(r"\s+", " ", str(s))).strip() for s in steps]
    steps = [s for s in steps if s]
    zh = bool(ri.CJK_RE.search(name + when))
    if not name or len(name) > (30 if zh else 80) or not when or len(when) > (120 if zh else 260):
        return None, "name or use_when missing or too long"
    if not 1 <= len(steps) <= 7 or any(len(s) > (160 if zh else 320) for s in steps):
        return None, "steps: 1 to 7, one sentence each"
    texts = [name, when] + steps
    if any(answer_cards.secret_like(t) for t in texts):
        return None, "key-shaped text"
    src = [by_id[c] for c in cids]
    source = _source_text(src)
    loose = experience.unsupported_figures({"situation": " ".join(texts)}, source)
    if loose:
        return None, f"numbers not in the cards: {', '.join(loose[:4])}"
    shared = set(ri.tokens(" ".join(steps))) & set(ri.tokens(source)) - ri.EN_FUNCTION - ri.QUERY_STOP
    if len(shared) < 2:
        return None, "the steps share no words with the cards"
    return {"cards": cids, "name": name, "use_when": when, "steps": steps[:7]}, ""


def parse(text: str, by_id: dict[str, dict], singles: set[str], covered: set[str]) -> tuple[list[dict], list[str]]:
    """Drafts that hold up from one reply (at most MAX_DRAFTS, no card in two drafts), and why the rest were dropped."""
    drafts, dropped, taken = [], [], set(covered)
    for item in experience._json_array(redact(text or "")):
        d, why = check(item, by_id, singles, taken)
        if d is None:
            dropped.append(why)
            continue
        if len(drafts) >= MAX_DRAFTS:
            dropped.append("over the night's cap")
            continue
        drafts.append(d)
        taken |= set(d["cards"])
    return drafts, dropped


# ---------- 写技能页 ----------

def skill_id(draft: dict, taken: set[str]) -> str:
    base = hashlib.sha1((draft["name"] + "|" + ",".join(sorted(draft["cards"]))).encode("utf-8")).hexdigest()
    for i in range(0, 36, 4):
        sid = "S" + base[i:i + 4]
        if sid not in taken:
            return sid
    return "S" + base[:6]


def file_name(name: str, sid: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|#^\[\]\n]', "", name).strip()[:50] or sid
    return f"技能｜{safe}.md" if ri.CJK_RE.search(safe) else f"Skill - {safe}.md"


def page_text(vault: Path, draft: dict, sid: str, cards: list[dict], used: dict, day: str, lane: str = "") -> str:
    zh = bool(ri.CJK_RE.search(draft["name"] + draft["use_when"]))
    title = f"技能｜{draft['name']}" if zh else f"Skill: {draft['name']}"
    when = draft["use_when"].replace('"', "'")
    head = ("---\n"
            f"title: \"{title}\"\n"
            f"type: {TYPE}\n"
            "status: draft\n"
            f"skill_id: {sid}\n"
            f"use_when: \"{when}\"\n"
            f"cards: {'; '.join(draft['cards'])}\n"
            f"drafted: {day}\n"
            "source: krouter-skills\n"
            "---\n\n"
            f"# {title}\n\n")
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(draft["steps"], 1))
    by_id = {c["id"]: c for c in cards}
    src_lines = []
    for cid in draft["cards"]:
        c = by_id.get(cid)
        u = used.get(cid, {})
        if not c:
            continue
        link = f"[[{zones.canon(vault, c['rel']).removesuffix('.md')}]]"
        origin = f"；最早来自 {c['source']}" if zh and c.get("source") else (f"; first from {c['source']}" if c.get("source") else "")
        src_lines.append(f"- 经验卡〔{cid}〕{link}：采纳 {u.get('adopted', 0)} 次、又遇到 {u.get('again', 0)} 次{origin}" if zh else
                         f"- Card [{cid}] {link}: adopted {u.get('adopted', 0)}, seen again {u.get('again', 0)}{origin}")
    sess = sessions_of(vault, set(draft["cards"]))
    if sess:
        src_lines.append(("- 会话（采纳或又遇到的那几次）：" if zh else "- Sessions (where it was adopted or came up again): ")
                         + ("、" if zh else ", ").join(f"`{s}`" for s in sess[-12:]))
    by = f"，借 {lane} 起草" if zh and lane else (f", drafted through {lane}" if lane else "")
    if zh:
        src_lines.append(f"- {day} 夜间流程起草{by}；是草稿，没人核对过。被采纳满 {PROMOTE_ADOPTED} 次自动转正；"
                         f"{WITHDRAW_DAYS} 天没人采纳、或提出 {WITHDRAW_OFFERED} 次没人采纳，自动撤回。不对就改、删，或撤销这一轮。")
        return head + f"**什么时候用**：{draft['use_when']}\n\n## 做法\n\n{steps}\n\n## 出处\n\n" + "\n".join(src_lines) + "\n"
    src_lines.append(f"- Drafted by the nightly run on {day}{by}; a draft nobody has checked. Adopted {PROMOTE_ADOPTED} "
                     f"times, it becomes active; not adopted in {WITHDRAW_DAYS} days, or offered {WITHDRAW_OFFERED} times "
                     "and never adopted, it is withdrawn. Fix it, delete it, or undo the run if it is wrong.")
    return head + f"**When to use**: {draft['use_when']}\n\n## Steps\n\n{steps}\n\n## Sources\n\n" + "\n".join(src_lines) + "\n"


def _set_status(path: Path, fields: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    end = text.index("\n---", 4)
    lines = text[4:end].splitlines()
    for key, val in fields.items():
        for i, line in enumerate(lines):
            if line.startswith(key + ":"):
                lines[i] = f"{key}: {val}"
                break
        else:
            lines.append(f"{key}: {val}")
    path.write_text("---\n" + "\n".join(lines) + text[end:], encoding="utf-8")


def _commit(vault: Path, rid: str, path: Path, summary: str, entry: str) -> str:
    """One change: the page in its own tagged commit, the ledger line in another (undo keeps the record)."""
    import capture_ledger

    undo = f"python3 {HERE / 'skills.py'} --vault '{vault}' undo {rid}"
    sha = capture_ledger.commit(vault, rid, [path], summary)
    where = f"提交 `{sha[:10]}`；" if sha else "库不是 git 仓库，没有提交可撤；"
    ledger = capture_ledger.append(vault, f"## {datetime.now().strftime('%Y-%m-%d %H:%M')} · run {rid}\n\n"
                                          f"{where}撤销这一条：`{undo}`\n\n{entry}\n")
    if sha:
        capture_ledger.commit(vault, rid, [ledger], f"变更记录 run {rid}", tagged=False)
    return sha


def _rid(sid: str, kind: str) -> str:
    import capture_ledger

    return f"{capture_ledger.run_id()}-{kind}-{sid}"


def _link(vault: Path, rel: str) -> str:
    return f"[[{zones.canon(vault, rel).removesuffix('.md')}]]"


def write_draft(vault: Path, draft: dict, cards: list[dict], used: dict, lane: str = "", day: str = "") -> dict:
    """Write one checked draft as its own commit. Returns {id, name, rel, cards, evidence, commit}."""
    day = day or date.today().isoformat()
    taken = {s["id"] for s in load(vault, include_retired=True)} | {c["id"] for c in cards}
    sid = skill_id(draft, taken)
    folder = vault / ri.skills_rel(vault)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(draft["name"], sid)
    if path.exists():
        path = path.with_name(path.stem + f"-{sid}.md")
    path.write_text(redact(page_text(vault, draft, sid, cards, used, day, lane)), encoding="utf-8")
    rel = str(path.relative_to(vault)).replace(os.sep, "/")
    ev = {c: {"adopted": used.get(c, {}).get("adopted", 0), "again": used.get(c, {}).get("again", 0)} for c in draft["cards"]}
    basis = "、".join(f"〔{c}〕采纳 {v['adopted']}、又遇到 {v['again']}" for c, v in ev.items())
    why = "一张卡被反复证实" if len(draft["cards"]) == 1 else f"{len(draft['cards'])} 张卡是同一类处境"
    sha = _commit(vault, _rid(sid, "draft"), path, f"技能草稿：「{draft['name']}」（{why}；{basis}）",
                  f"- 技能草稿〔{sid}〕{_link(vault, rel)}：{why}；依据 {basis}。草稿只作为建议出现，被采纳满 "
                  f"{PROMOTE_ADOPTED} 次自动转正。")
    return {"id": sid, "name": draft["name"], "rel": rel, "cards": draft["cards"], "evidence": ev, "commit": sha[:10]}


# ---------- 转正、撤回、沉底（不调模型） ----------

def _days(since: str, today: date) -> int:
    try:
        return (today - date.fromisoformat(since[:10])).days
    except ValueError:
        return 0


def lifecycle(vault: Path, today: date | None = None, used: dict | None = None) -> dict:
    """Promote drafts adopted PROMOTE_ADOPTED times; withdraw drafts nobody adopted (WITHDRAW_DAYS, WITHDRAW_OFFERED)
    or whose cards are gone. Each change is one commit. Returns {promoted: [...], withdrawn: [...]}."""
    today = today or date.today()
    used = experience.usage(vault) if used is None else used
    live_cards = {c["id"] for c in experience.load_cards(vault)}
    promoted, withdrawn = [], []
    for s in load(vault):
        if s["status"] != "draft":
            continue
        u = used.get(s["id"], {})
        adopted, offered = int(u.get("adopted", 0)), int(u.get("offered", 0))
        age = _days(s["drafted"], today)
        if adopted >= PROMOTE_ADOPTED:
            _set_status(s["path"], {"status": "active", "promoted": today.isoformat()})
            sha = _commit(vault, _rid(s["id"], "promote"), s["path"],
                          f"技能转正：「{s['name']}」（被采纳 {adopted} 次，门槛 {PROMOTE_ADOPTED}；提出 {offered} 次）",
                          f"- 技能转正〔{s['id']}〕{_link(vault, s['rel'])}：被采纳 {adopted} 次（门槛 {PROMOTE_ADOPTED}），"
                          f"提出 {offered} 次，起草 {age} 天。")
            promoted.append({"id": s["id"], "name": s["name"], "adopted": adopted, "offered": offered, "days": age,
                             "commit": sha[:10]})
            continue
        why = ""
        if not [c for c in s["cards"] if c in live_cards]:
            why = "依据的经验卡都已撤下或删掉"
        elif adopted == 0 and offered >= WITHDRAW_OFFERED:
            why = f"提出 {offered} 次，一次没被采纳（门槛 {WITHDRAW_OFFERED}）"
        elif adopted == 0 and age >= WITHDRAW_DAYS:
            why = f"起草 {age} 天，一次没被采纳（门槛 {WITHDRAW_DAYS} 天）"
        if why:
            _set_status(s["path"], {"status": "retired", "retired": today.isoformat()})
            sha = _commit(vault, _rid(s["id"], "withdraw"), s["path"], f"技能草稿撤回：「{s['name']}」（{why}）",
                          f"- 技能草稿撤回〔{s['id']}〕{_link(vault, s['rel'])}：{why}。页面留着，`status: retired`。")
            withdrawn.append({"id": s["id"], "name": s["name"], "why": why, "adopted": adopted, "offered": offered,
                              "days": age, "commit": sha[:10]})
    return {"promoted": promoted, "withdrawn": withdrawn}


def undo(vault: Path, rid: str) -> dict:
    import capture_ledger

    return capture_ledger.undo(vault, rid)


# ---------- 会话开始时的摘要段：只列名字和什么时候用 ----------

HEAD = {
    "zh": "KRouter 技能：从你攒下的经验里长出来的做法，不是这个项目的事实。每行是「名字：什么时候用〔编号〕」，全文在「{folder}」。",
    "en": "KRouter skills: procedures grown from lessons collected on other tasks; not facts about this project. Each "
          "line is \"name: when to use it [id]\"; the full text is in \"{folder}\".",
}
DRAFT_HEAD = {
    "zh": "技能草稿（还没转正，只是建议，可能不对）：",
    "en": "Skill drafts (not yet confirmed; suggestions only, may be wrong):",
}
USE = {
    "zh": ("用法：只有当用户这次要做的事正好是某一行说的处境时，才用工具 krouter_skill（参数 id）取它的全文（没有这个工具就读"
           "上面文件夹里的那一页），照着步骤做，并在回复里说一句「按技能〈名字〉来〔编号〕」；处境不符就一个字都不要提，也不要说没有。"),
    "en": ("How to use: only when what the user is doing now is exactly the situation one line describes, fetch its full "
           "text with the tool krouter_skill (argument id; without that tool, read that page in the folder above), "
           "follow its steps, and say once in your reply \"Following the skill <name> [id]\". If none fits, say nothing "
           "about them at all, and do not say that there are none."),
}


def rank(skills: list[dict], used: dict) -> list[dict]:
    """Active skills first (most adopted first), then drafts; a draft offered SINK_OFFERED times and never adopted sinks."""
    def key(s: dict) -> tuple:
        u = used.get(s["id"], {})
        sunk = s["status"] == "draft" and not u.get("adopted") and u.get("offered", 0) >= SINK_OFFERED
        return (s["status"] == "active", not sunk, u.get("adopted", 0), s.get("promoted") or s.get("drafted"), s["rel"])
    return sorted(skills, key=key, reverse=True)


def line(s: dict, lang: str) -> str:
    when = re.sub(r"\s+", " ", s["use_when"]).strip().rstrip("。.")
    return f"- {s['name']}：{when}〔{s['id']}〕" if lang == "zh" else f"- {s['name']}: {when} [{s['id']}]"


def digest(vault: Path, used: dict | None = None) -> str:
    """The skills part of the session-start context; "" when off or when there are none."""
    if not on():
        return ""
    skills = load(vault)
    if not skills:
        return ""
    used = experience.usage(vault) if used is None else used
    lang = "en" if sum(s["lang"] == "en" for s in skills) * 2 > len(skills) else "zh"
    ordered = rank(skills, used)
    active = [s for s in ordered if s["status"] == "active"][:LIST_ACTIVE]
    drafts = [s for s in ordered if s["status"] == "draft"][:LIST_DRAFTS]
    out = [HEAD[lang].format(folder=ri.skills_rel(vault))]
    out += [line(s, lang) for s in active]
    if drafts:
        out += [DRAFT_HEAD[lang]] + [line(s, lang) for s in drafts]
    out.append(USE[lang])
    return redact("\n".join(out))


def listing(vault: Path) -> list[dict]:
    """[{id, name, use_when, status}] in digest order, for the MCP tool's description."""
    if not on():
        return []
    used = experience.usage(vault)
    ordered = rank(load(vault), used)
    return ([s for s in ordered if s["status"] == "active"][:LIST_ACTIVE]
            + [s for s in ordered if s["status"] == "draft"][:LIST_DRAFTS])


def show(vault: Path, sid: str) -> str:
    """The full page of one skill, as the host reads it ("" when there is no such skill)."""
    s = find(vault, sid)
    if not s:
        return ""
    text = s["path"].read_text(encoding="utf-8")
    note = {"draft": ("（这是草稿：还没转正，按步骤做之前想一想是否真的适用。）" if s["lang"] == "zh"
                      else "(This is a draft, not yet confirmed: check that it really applies before following it.)"),
            "active": ""}.get(s["status"], "（已撤回，不要再用。）" if s["lang"] == "zh" else "(Withdrawn: do not use it.)")
    return redact((note + "\n\n" if note else "") + ri.split_frontmatter(text)[1].strip() + f"\n\n(skill_id: {s['id']}, status: {s['status']})")


def record_fetch(vault: Path, sid: str, who: str) -> None:
    """One `fetched` line in the use records: a host took the full text (not an adoption)."""
    path = zones.path(vault, experience.USES)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "card": sid, "kind": "fetched", "session": who,
           "turn": "", "why": "krouter_skill"}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------- 导出成某个应用自己的技能格式（显式命令，默认不做） ----------

APPS = {"claude": ("agent-skills", "~/.claude/skills"), "codex": ("agent-skills", "~/.codex/skills"),
        "cursor": ("cursor-rule", ".cursor/rules")}
EXPORT_MANIFEST = ".krouter-skills-export.json"


def _slug(s: dict) -> str:
    ascii_name = re.sub(r"[^a-z0-9]+", "-", s["name"].lower()).strip("-")[:40]
    return f"krouter-{ascii_name}" if ascii_name and not ri.CJK_RE.search(s["name"]) else f"krouter-skill-{s['id'].lower()}"


def export(vault: Path, fmt: str, dest: Path, drafts: bool = False) -> dict:
    """Write active skills (and drafts with `drafts`) into `dest` in an app's own format: `agent-skills`
    (`<dest>/<slug>/SKILL.md` with name and description, as Claude Code and Codex read them) or `cursor-rule`
    (`<dest>/<slug>.mdc`). Files this command wrote before and no longer exports are removed; nothing else is touched."""
    dest = Path(dest).expanduser()
    want = [s for s in load(vault) if s["status"] == "active" or (drafts and s["status"] == "draft")]
    dest.mkdir(parents=True, exist_ok=True)
    man_path = dest / EXPORT_MANIFEST
    try:
        before = json.loads(man_path.read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError):
        before = []
    written = []
    for s in want:
        body = ri.split_frontmatter(s["path"].read_text(encoding="utf-8"))[1].strip()
        desc = re.sub(r"\s+", " ", s["use_when"]).replace('"', "'")
        desc += (f"（KRouter 技能 {s['id']}{'，草稿' if s['status'] == 'draft' else ''}）" if s["lang"] == "zh"
                 else f" (KRouter skill {s['id']}{', draft' if s['status'] == 'draft' else ''})")
        slug = _slug(s)
        if fmt == "agent-skills":
            rel = f"{slug}/SKILL.md"
            text = f"---\nname: {slug}\ndescription: \"{desc}\"\n---\n\n{body}\n"
        elif fmt == "cursor-rule":
            rel = f"{slug}.mdc"
            text = f"---\ndescription: \"{desc}\"\nalwaysApply: false\n---\n\n{body}\n"
        else:
            raise ValueError(f"unknown format {fmt!r}: agent-skills or cursor-rule")
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redact(text), encoding="utf-8")
        written.append(rel)
    removed = []
    for rel in before:
        if rel not in written and (dest / rel).is_file():
            (dest / rel).unlink()
            if rel.endswith("/SKILL.md"):
                try:
                    (dest / rel).parent.rmdir()
                except OSError:
                    pass
            removed.append(rel)
    man_path.write_text(json.dumps({"by": "krouter skills.py export", "format": fmt, "files": written},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"export": "done", "format": fmt, "dest": str(dest), "written": written, "removed": removed}


# ---------- 夜间一步 ----------

def _state_file() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "skills-draft.json"


def _signature(vault: Path, pool: list[dict], singles: list[dict]) -> str:
    raw = json.dumps([str(Path(vault).resolve()), sorted(c["id"] for c in pool), sorted(c["id"] for c in singles)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _seen(vault: Path) -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember(vault: Path, sig: str) -> None:
    data = _seen(vault)
    data[str(Path(vault).resolve())] = sig
    try:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def draft_step(vault: Path, dry: bool = False, force: bool = False) -> dict:
    """At most one model call: draft skills from the cards that could grow into one. Returns the nightly row's part."""
    cards = experience.load_cards(vault)
    for c in cards:
        c["path"] = vault / c["rel"]
    used = experience.usage(vault)
    skills = load(vault)
    cand = candidates(vault, cards, used, skills)
    pool, singles = cand["pool"], cand["singles"]
    if not singles and len(pool) < GROUP_MIN:
        return {"drafting": "nothing to draft", "drafted": [], "calls": 0}
    sig = _signature(vault, pool, singles)
    if not force and _seen(vault).get(str(Path(vault).resolve())) == sig:
        return {"drafting": "unchanged since the last attempt", "drafted": [], "calls": 0}
    text, _lang = prompt(vault, pool, singles, skills, used)
    if dry:
        return {"drafting": "dry-run", "chars": len(text), "writes": [FOLDER + "/…"], "drafted": [], "calls": 0}
    import llm

    try:
        reply = llm.complete(text, vault)
    except llm.NoModel as exc:
        return {"drafting": "skipped: no model lane", "why": str(exc)[:160], "drafted": [], "calls": 0}
    except Exception as exc:  # noqa: BLE001  模型调用失败：记下原因，下一晚再试
        return {"drafting": "failed", "why": str(exc)[:200], "drafted": [], "calls": 1}
    _remember(vault, sig)
    by_id = {c["id"]: c for c in pool}
    drafts, dropped = parse(reply, by_id, {c["id"] for c in singles}, cand["covered"])
    lane = ""
    try:
        steps = llm.plan(vault)
        lane = (f"cli {Path(steps[0][1]).name}" if steps[0][0] == "cli" else steps[0][0]) if steps else ""
    except Exception:  # noqa: BLE001
        pass
    written = [write_draft(vault, d, cards, used, lane) for d in drafts]
    # 模型看过的、没被起草的卡：下一晚卡没变就不再问（起草后剩下的这批卡也记下）
    rest = candidates(vault, cards, used)
    _remember(vault, _signature(vault, rest["pool"], rest["singles"]))
    return {"drafting": "ran", "drafted": written, "dropped": dropped, "calls": 1, "chars": len(text)}


def nightly(vault: Path, dry: bool = False, force: bool = False) -> dict:
    if not on():
        return {"skills": "off"}
    if dry:
        return {"skills": "dry-run", **draft_step(vault, dry=True, force=force)}
    life = lifecycle(vault)  # 先转正、撤回（不调模型），再起草：撤回的卡下一步可以重新起草
    row = draft_step(vault, force=force)
    return {"skills": "done", **row, **life}


def report_lines(row: dict) -> list[str]:
    """The nightly report's lines for this step: what was drafted, promoted, withdrawn, and on what counts."""
    if not row or row.get("skills") in (None, "off", "dry-run"):
        return []
    out = ["技能（经验长成的做法；草稿只作为建议出现，被采纳满 "
           f"{PROMOTE_ADOPTED} 次自动转正，{WITHDRAW_DAYS} 天或提出 {WITHDRAW_OFFERED} 次没人采纳自动撤回）：", ""]
    state = row.get("drafting", "")
    if state.startswith("skipped"):
        out.append("- 起草：跳过，没有可用的模型通道（没有 API key，也没找到已登录的 agent 命令行）；转正和撤回照常（不用模型）。")
    elif state == "failed":
        out.append(f"- 起草：模型调用失败（{row.get('why', '')[:120]}），下一晚再试。")
    elif state == "ran" and not row.get("drafted"):
        out.append("- 起草：问过模型，没有值得起草的" + (f"（丢掉 {len(row.get('dropped') or [])} 份没过检查的）" if row.get("dropped") else "") + "。")
    elif state in ("nothing to draft", "unchanged since the last attempt"):
        out.append("- 起草：" + ("没有能长成技能的经验（没有被反复证实的卡，未归入技能的卡不到两张）" if state == "nothing to draft"
                                else "经验卡和上次问模型时一样，没再调用") + "。")
    for d in row.get("drafted") or []:
        basis = "、".join(f"〔{c}〕采纳 {v['adopted']}、又遇到 {v['again']}" for c, v in d["evidence"].items())
        out.append(f"- 新起草〔{d['id']}〕[[{d['rel'].removesuffix('.md')}]]：依据 {basis}")
    for p in row.get("promoted") or []:
        out.append(f"- 转正〔{p['id']}〕「{p['name']}」：被采纳 {p['adopted']} 次（门槛 {PROMOTE_ADOPTED}），提出 {p['offered']} 次")
    for w in row.get("withdrawn") or []:
        out.append(f"- 撤回〔{w['id']}〕「{w['name']}」：{w['why']}")
    if len(out) == 2:
        return []
    return out + ["", "每一条是单独一个 git 提交，`skills.py undo <run>` 撤销（run 见「记忆变更记录」）。", ""]


def main() -> int:
    import argparse

    from krouter_home import vault_path

    ap = argparse.ArgumentParser(description="Skills grown from experience cards: the nightly step, listing, full "
                                             "text, export, undo.")
    ap.add_argument("--vault", default=vault_path())
    ap.add_argument("--cli", default="", help="pick a CLI explicitly for drafting")
    ap.add_argument("--model", default="")
    ap.add_argument("--dry-run", action="store_true", help="no model call, no write: what drafting would send")
    ap.add_argument("--force", action="store_true", help="draft even when the cards are as at the last attempt")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("nightly", help="promote / withdraw, then draft (the default)")
    sub.add_parser("list", help="the skills part of the session-start digest")
    sp = sub.add_parser("show", help="one skill's full text")
    sp.add_argument("id")
    ep = sub.add_parser("export", help="write skills in an app's own format (only when you run this)")
    ep.add_argument("--app", choices=sorted(APPS), help="claude (~/.claude/skills), codex (~/.codex/skills), cursor "
                                                        "(.cursor/rules in the current folder)")
    ep.add_argument("--format", choices=("agent-skills", "cursor-rule"))
    ep.add_argument("--dest", default="", help="where to write; overrides --app's folder")
    ep.add_argument("--drafts", action="store_true", help="export drafts too (default: active skills only)")
    up = sub.add_parser("undo", help="revert one draft, promotion or withdrawal (run id from the change ledger)")
    up.add_argument("run")
    args = ap.parse_args()
    if not args.vault:
        print("set KROUTER_VAULT (or the older name OBSIDIAN_VAULT)", file=sys.stderr)
        return 2
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    vault = Path(args.vault).expanduser()
    if args.cmd == "list":
        print(digest(vault) or "(no skills)")
        return 0
    if args.cmd == "show":
        text = show(vault, args.id)
        print(text or f"no skill {args.id}")
        return 0 if text else 1
    if args.cmd == "export":
        if not (args.dest or args.app):
            print("export: name --app or --dest", file=sys.stderr)
            return 2
        fmt = args.format or (APPS[args.app][0] if args.app else "agent-skills")
        dest = Path(args.dest) if args.dest else Path(APPS[args.app][1])
        print(json.dumps(export(vault, fmt, dest, args.drafts), ensure_ascii=False))
        return 0
    if args.cmd == "undo":
        res = undo(vault, args.run)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("undo") == "done" else 1
    row = nightly(vault, dry=args.dry_run, force=args.force)
    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
