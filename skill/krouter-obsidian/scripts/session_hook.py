#!/usr/bin/env python3
"""Agent hooks (Claude Code, Codex, Cursor): remember each turn as it ends, bring this project's decisions when a session
starts, note a correction the moment you type it.

The two things that make claude-mem feel like memory, done the KRouter way: what is captured is a plain Markdown
page you can read and fix, and what is brought back is a handful of decisions, each with the page it came from.

`session_hook.py turn` (Stop: the agent finished a turn): imports the session so far (`import_sessions.py --file …
--local`), in the background, with no model call, so what was just said is in the vault before the next question, and
another window's agent can find it. A digest made earlier stays on the page.

`session_hook.py end` (SessionEnd): imports the session that just ended (`import_sessions.py --file`), in the
background so the agent is not held up; it also distills that session when you said yes to distilling. Nothing
happens before you said yes to importing (`import_sessions.py --consent`, or the install).

`session_hook.py start` (SessionStart): prints, as context for the new session, up to 8 decisions recorded for this
repository (matched by its git top level, never by folder name) in the last 30 days, each naming its page,
corrections first. A decision that a later correction replaced ("原来 A → 改成 B") is left out, so the new session
does not start from the old answer. Every distilled line counts (distilling writes memory without a yes; what it
wrote is in the change ledger); `KROUTER_INJECT=confirmed` brings only pages marked `confirmed: true` / `status:
active` plus corrections, as before 1.3, `KROUTER_INJECT=0` nothing. Nothing is printed when the vault
has none or the import was never turned on. In English unless the lines are Chinese. Reads only the vault; sends
nothing; well under a second.

`session_hook.py prompt` (UserPromptSubmit): when what you just typed reads like a correction ("改成 B", "以后一律",
"锁死", "from now on", "that's wrong"), it appends what you typed, redacted and cut to 300 characters, to the day's
`05 时间日志/会话摘录/YYYY-MM-DD｜纠正候选.md`, marked provisional; the next distill of that session settles it on its own (`corrections.py`). Local pattern match
only, no model call, nothing sent; a rhetorical question ("不是吗", "对不对") is not a correction. It does nothing
before you said yes to importing, for a prompt over 1500 characters, under a KRouter model call (`KROUTER_IN_DISTILL`),
or in a session marked `#不记`.

All four read the hook's JSON on stdin and never fail the session. `--agent` says whose hook it is (default `claude`):

| | Claude Code (plugin) | Codex (`~/.codex/hooks.json`) | Cursor (`~/.cursor/hooks.json`) |
|---|---|---|---|
| start | `SessionStart` | `SessionStart` | `sessionStart`, prints `additional_context` |
| prompt | `UserPromptSubmit` | `UserPromptSubmit` (prints nothing: Codex adds plain output to the context) | `beforeSubmitPrompt`, always `{"continue": true}` |
| turn | `Stop` | `Stop` | `stop`, prints `{}` (never a follow-up message) |
| end | `SessionEnd`, `PreCompact` | `SessionEnd` | `sessionEnd` |

Codex and Claude Code send `session_id`, `transcript_path`, `cwd` (and `prompt`); Cursor sends `conversation_id`,
`workspace_roots` and `transcript_path`. A missing transcript path is looked up by the session id. Under a KRouter
model call (`KROUTER_IN_DISTILL`) none of them does anything.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zones  # noqa: E402
from krouter_home import project_root, vault_path  # noqa: E402
from krouter_redact import redact  # noqa: E402

DAYS = 30
MAX_LINES = 8
MAX_CHARS = 1600
DIGEST_HEADS = ("## 定了什么、改了什么（模型提炼）", "## 定了什么、改了什么（模型提炼，待你确认）",
                "## 现在有效的、被取代的（模型整理，待你确认）")
OLD_SIDE = re.compile(r"^(原来|以前|之前|起初|最初|was|from|before|previously)\s*[:：]?\s*", re.I)
NEW_SIDE = re.compile(r"^(改成|改为|改回|换成|换回|变成|现在|now|back to|to|became)\s*[:：]?\s*", re.I)
TIME = re.compile(r"[（(]\s*(\d{1,2}):(\d{2})\s*[)）]")
# 纠正用语：说的是"以后照这个来"或"刚才那个不对"，不是提问
CORRECTION = re.compile(r"(改成|改为|改回|换成|换回|以后都|以后一律|一律|锁死|(?<!要)不要再|别再|记住|纠正|纠错|搞错|说错|弄错|你错了|"
                        r"不对[，,。！!]|应该是|from now on|instead of|that'?s wrong|that is wrong|don'?t ever|never again|"
                        r"stop doing|always use|you got it wrong)", re.I)
# 反问不是纠正："……不是吗""对不对""难道不是"
RHETORICAL = re.compile(r"(不是吗|对不对|是不是|难道不是|对吧|好不好|行不行|可不可以|能不能|isn'?t it|right\?)\s*[？?！!。]*\s*$",
                        re.I)
# 普通提问不是纠正："……有 ECC 纠错吗""应该是这样吗？"
QUESTION = re.compile(r"(吗|呢|么|[？?])\s*$")
# 应用替你附上的上下文块、你粘贴进来的整段：不是你此刻说的话，记之前先去掉
ATTACHED = re.compile(r"<([A-Za-z][\w-]*)\b[^>]*>.*?</\1>|<[A-Za-z][\w-]*\b[^>]*/>"
                      r"|<(?:pasted_content|artifact-view-context|system-reminder|ide_[\w-]+)\b[^>]*>.*\Z", re.S)  # 没闭合的整段也算
NO_CAPTURE = re.compile(r"#(不记|nocapture)(?![0-9A-Za-z_])", re.I)
PROMPT_MAX = 1500
CANDIDATE_MAX = 300
CANDIDATES = "05 时间日志/会话摘录"


AGENTS = {"claude": "claude", "codex": "codex", "cursor": "cursor"}  # --agent → 候选行里的会话前缀


def consented() -> bool:
    base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")
    for name in ("import.json", "import-claude-mem.json"):
        try:
            if json.loads((base / name).read_text(encoding="utf-8")).get("consent"):
                return True
        except (OSError, ValueError):
            continue
    return False


def meta_of(text: str) -> dict[str, str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}
    out = {}
    for line in text[4:].split("\n---", 1)[0].splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def digest_lines(text: str) -> list[str]:
    for head in DIGEST_HEADS:
        if head in text:
            block = text.split(head, 1)[1].split("\n## ", 1)[0]
            return [ln.strip() for ln in block.splitlines() if ln.strip().startswith(("-", "*"))
                    and "没有定下来的事" not in ln]
    return []


def terms(text: str) -> set[str]:
    """Content words of a decision line (time stamps and function words dropped), for matching a line to the old
    side of a later correction."""
    import recall_index as ri

    text = re.sub(r"[（(]\s*\d{1,2}:\d{2}\s*[)）]", " ", text)
    return {t for t in ri.question_terms(text) if t not in ri.EN_FUNCTION}


def sides(line: str) -> tuple[set[str], set[str]] | None:
    """(old side, new side) of a correction line "原来 A → 改成 B"; None for a plain decision."""
    if "→" not in line:
        return None
    old, new = line.split("→", 1)
    return terms(OLD_SIDE.sub("", old.strip())), terms(NEW_SIDE.sub("", new.strip()))


def specific(words: set[str]) -> set[str]:
    """The tokens that carry a value (a number, a name, an English word), not just the subject's shared vocabulary."""
    return {t for t in words if re.search(r"[0-9a-z]", t)}


def changed(old: set[str], new: set[str]) -> tuple[set[str], set[str]]:
    """(the value that was replaced, the value that replaced it): what one side has and the other does not, narrowed
    to value-carrying tokens when there are any ("8080" and "9090", not "本地 API 端口")."""
    gone, came = old - new, new - old
    return (specific(gone) or gone), (specific(came) or came)


def holds(value: set[str], line: set[str], share: float = 1.0) -> bool:
    return bool(value) and len(value & line) >= share * len(value)


def stale_lines(found: list[tuple[str, str, str, bool]]) -> tuple[set[int], set[int]]:
    """Indices of recorded lines a later correction replaced. Order is the page date, then the line's (HH:MM), then its
    place on the page; a correction only replaces what came before it.

    A plain line is replaced when it still holds the value a later correction replaced (all of it: "端口用 8080" holds
    "8080"; "端口文档放在 README" does not) and does not already hold the new one; it comes back when an even later
    correction restores its value (same-day revert). A correction is replaced when a later one starts from its new
    value on the same subject (30 → 10, then 10 → 5).

    Returns (replaced, unsure): a line that holds the replaced value but only part of the correction's subject
    ("测试环境 API 端口用 8080" against "本地 API 端口 8080 → 9090") is not dropped; it is marked for the agent to check."""
    keyed = []
    for n, (day, line, _, _) in enumerate(found):
        m = TIME.search(line)
        keyed.append(((day, f"{int(m.group(1)):02d}:{m.group(2)}" if m else "", n), line))
    order = sorted(range(len(found)), key=lambda i: keyed[i][0])
    pos = {i: k for k, i in enumerate(order)}
    fixes = [(i, *sides(found[i][1])) for i in order if sides(found[i][1])]
    out, unsure = set(), set()
    for i, (_, line, _, _) in enumerate(found):
        mine = terms(line)
        after = [(j, old, new) for j, old, new in fixes if pos[j] > pos[i]]
        if sides(line) is None:
            for k, (j, old, new) in enumerate(after):
                gone, came = changed(old, new)
                # 主题：旧一侧里不是数值的词（「会议 时长」），「分钟」这种两侧都有的单位不算
                subject = (old - new) - specific(old - new)
                if holds(gone, mine) and not holds(came, mine, 0.5) and (not subject or subject & mine):
                    back = [(o2, n2) for _, o2, n2 in after[k + 1:] if holds(changed(o2, n2)[1], mine)]
                    if back:
                        continue
                    if not subject or subject <= mine:
                        out.add(i)
                        break
                    unsure.add(i)  # 值对得上、主语只对上一部分：别的环境、别的服务，不删，提醒核对
        else:
            old1, new1 = sides(line)
            came1 = changed(old1, new1)[1]
            subject1 = (old1 | new1) - came1 - changed(old1, new1)[0]
            for j, old2, new2 in after:
                if holds(came1, old2) and (not subject1 or subject1 & old2):
                    out.add(i)
                    break
    return out, unsure - out


CONFIRMED = {"active", "confirmed", "adopted"}
MAYBE_CHANGED = {"zh": "（可能已被上面的「→」改过，先核对）", "en": " (may have been changed by a \"→\" line above; check)"}
CJK = re.compile(r"[\u3400-\u9fff]")


def project_lines(vault: Path, root: str, everything: bool = False) -> list[tuple[str, str, bool]]:
    """[(line, page, confirmed)] for the project at `root`, corrections first, then newest first.

    A page counts only when its `project_root` is this repo: two repos that are both called `api` never share
    decisions. Pages from before 1.0.1 have no `project_root` and are left out until re-imported. With `everything`
    (the default) every distilled line comes; without it (`KROUTER_INJECT=confirmed`) only pages you confirmed
    (`status: active`, or `confirmed: true`) bring every line, the rest only corrections ("A → B")."""
    if not root:
        return []
    cut = (date.today() - timedelta(days=DAYS)).isoformat()
    found: list[tuple[str, str, str, bool]] = []
    for folder in ("05 时间日志/会话摘录", "02 经验与方法/从 claude-mem 导入"):
        d = zones.path(vault, folder)
        if not d.is_dir():
            continue
        for page in d.glob("*.md"):
            try:
                text = page.read_text(encoding="utf-8")
            except OSError:
                continue
            meta = meta_of(text)
            if meta.get("project_root") != root or (meta.get("date") and meta["date"] < cut):
                continue
            ok = meta.get("status", "").lower() in CONFIRMED or meta.get("confirmed", "").lower() == "true"
            rel = zones.canon(vault, str(page.relative_to(vault)).replace(os.sep, "/"))
            for ln in digest_lines(text):
                line = re.sub(r"^[-*]\s*", "", ln)
                if ok or everything or "→" in line:
                    found.append((meta.get("date") or "9999", line, rel, ok))
    found.sort(key=lambda x: x[0], reverse=True)
    # 后来改过主意的：旧决定不再当现行决定带进新会话（纠错那一行本身就写着「原来 A → 改成 B」）
    gone, unsure = stale_lines(found)
    found = [(d, line + (MAYBE_CHANGED["zh" if CJK.search(line) else "en"] if n in unsure else ""), rel, ok)
             for n, (d, line, rel, ok) in enumerate(found) if n not in gone]
    seen, out = set(), []
    for _, line, rel, ok in sorted(found, key=lambda x: "→" not in x[1]):  # 稳定排序：纠错在前，其余仍按新到旧
        if line not in seen:
            seen.add(line)
            out.append((line, rel, ok))
    return out[:MAX_LINES]


HEAD = {
    "zh": ("KRouter：这个仓库（{name}）最近 {days} 天在你的库里记下的决定（模型从会话里提炼，括号里是来源页）。"
           "「→」是改过主意的，以箭头后面为准："),
    "en": ("KRouter: decisions recorded in your vault for this repository ({name}) in the last {days} days, distilled "
           "from sessions by a model (source page in brackets). \"→\" marks a change of mind; the side after it holds:"),
}
TAIL = {"zh": "其他问题先用 krouter_ask 查库；库里没有（recall: none）就直说，不要猜。",
        "en": "For anything else, ask the vault with krouter_ask first; if it says recall: none, say so instead of guessing."}
MARK_UNCONFIRMED = {"zh": "（待确认）", "en": " (unconfirmed)"}


def normalize(payload: dict, agent: str) -> dict:
    """The fields the handlers read (`session_id`, `transcript_path`, `cwd`, `prompt`), whichever agent sent the hook."""
    p = dict(payload)
    p["session_id"] = str(p.get("session_id") or p.get("conversation_id") or "")
    if not p.get("cwd"):
        roots = p.get("workspace_roots")
        p["cwd"] = str(roots[0]) if isinstance(roots, list) and roots else ""
    path = str(p.get("transcript_path") or "")
    if agent in ("codex", "cursor") and p["session_id"] and not (path and Path(path).is_file()):
        import import_sessions

        found = import_sessions.find_transcript(agent, p["session_id"])
        p["transcript_path"] = str(found) if found else path
    return p


def start(payload: dict, agent: str = "claude") -> int:
    mode = os.environ.get("KROUTER_INJECT", "")
    if mode == "0" or not consented():
        return 0
    raw = vault_path()
    if not raw or not Path(raw).is_dir():
        return 0
    root = project_root(payload.get("cwd") or os.getcwd())
    strict = mode == "confirmed"
    lines = project_lines(Path(raw), root, everything=not strict)
    if not lines:
        return 0
    lang = "zh" if any(CJK.search(line) for line, _, _ in lines) else "en"
    body = [HEAD[lang].format(name=Path(root).name, days=DAYS)]
    for line, rel, ok in lines:
        body.append(f"- {line}{MARK_UNCONFIRMED[lang] if strict and not ok else ''} 〔{rel}〕")
    body.append(TAIL[lang])
    text = redact("\n".join(body))[:MAX_CHARS]
    if agent == "cursor":
        print(json.dumps({"additional_context": text}, ensure_ascii=False))
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}},
                         ensure_ascii=False))
    return 0


def end(payload: dict, agent: str = "claude", local: bool = False) -> int:
    transcript = payload.get("transcript_path") or ""
    if not transcript or os.environ.get("KROUTER_IN_DISTILL") or not consented():
        return 0
    raw = vault_path()
    if not raw:
        return 0
    log = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "session-hook.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(HERE / "import_sessions.py"), "--vault", raw, "--file", transcript,
            *(["--local"] if local else [])]
    with log.open("a", encoding="utf-8") as fh:
        kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}  # DETACHED_PROCESS
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
                         env={**os.environ, "OBSIDIAN_VAULT": raw}, **kw)
    return 0


def correction_cue(text: str) -> str:
    """The correction word a prompt uses, or "" when it is not a correction (none found, or the sentence that holds
    it ends as a rhetorical question)."""
    for sentence in re.split(r"(?<=[。！!？?\n])", text):
        m = CORRECTION.search(sentence)
        s = sentence.strip()
        if m and not RHETORICAL.search(s) and not QUESTION.search(s.rstrip("。！! ")):
            return m.group(1)
    return ""


def own_words(text: str) -> str:
    """What the person typed: the prompt without the blocks the app attached or the person pasted in."""
    return ATTACHED.sub(" ", text).strip()


def turn(payload: dict, agent: str = "claude") -> int:
    return end(payload, agent, local=True)


def marked_out(transcript: Path, agent: str = "claude") -> bool:
    """An earlier question of this session carries `#不记`. Only what the person typed counts: an agent's answer or a
    tool's output that merely mentions the marker does not."""
    if agent != "claude":
        import import_sessions

        try:
            turns = import_sessions.READERS[import_sessions.agent_of(transcript)](transcript)["turns"]
        except (OSError, ValueError, KeyError):
            return False
        return any(NO_CAPTURE.search(t["ask"]) for t in turns)
    try:
        with transcript.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if "#" not in raw or '"user"' not in raw:
                    continue
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                msg = d.get("message") if isinstance(d, dict) and d.get("type") == "user" else None
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str) and NO_CAPTURE.search(content):
                    return True
    except OSError:
        return False
    return False


def prompt(payload: dict, agent: str = "claude") -> int:
    text = own_words(str(payload.get("prompt") or ""))
    if (not text.strip() or len(text) > PROMPT_MAX or os.environ.get("KROUTER_IN_DISTILL") or NO_CAPTURE.search(text)
            or not consented()):
        return 0
    cue = correction_cue(text)
    raw = vault_path()
    if not cue or not raw:
        return 0
    sid = str(payload.get("session_id") or "")
    transcript = str(payload.get("transcript_path") or "")
    if transcript and marked_out(Path(transcript), agent):
        return 0  # 这个会话前面标过不记
    vault = Path(raw).expanduser()
    now = datetime.now()
    folder = zones.path(vault, CANDIDATES)
    page = folder / f"{now.date().isoformat()}｜纠正候选.md"
    said = re.sub(r"\s+", " ", redact(text)).strip()
    if len(said) > CANDIDATE_MAX:
        said = said[:CANDIDATE_MAX].rstrip() + " …"
    cwd = str(payload.get("cwd") or "")
    project = Path(project_root(cwd)).name if cwd else ""
    line = (f"- （{now.strftime('%H:%M')}）{said} — 项目 {project or '未知'}，会话 `{AGENTS.get(agent, 'claude')}:{sid[:8] or '?'}`，"
            f"命中「{cue}」，待下次蒸馏判定\n")
    folder.mkdir(parents=True, exist_ok=True)
    if not page.exists():
        page.write_text("---\n"
                        f"title: \"{now.date().isoformat()} 纠正候选\"\n"
                        "type: correction-candidates\n"
                        "status: provisional\n"
                        f"date: {now.date().isoformat()}\n"
                        "source: krouter-hook\n"
                        "---\n\n"
                        f"# {now.date().isoformat()} 纠正候选\n\n"
                        "你在会话里说过、读起来像纠正的话，hook 当场照录（已脱敏）。下一次增量蒸馏自动判定：成立的写进那个会话的提炼，"
                        "不成立的就地标掉，两种都记进「记忆变更记录」。\n\n",
                        encoding="utf-8")
    with page.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return 0


# Cursor 要的回执：提问照常发出；一轮结束不追加任何消息（stop 的 followup_message 会被当成下一条提问）
CURSOR_REPLY = {"prompt": {"continue": True}, "turn": {}}


def main() -> int:
    argv = sys.argv[1:]
    which = argv[0] if argv else ""
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv[:-1] else "claude"
    agent = agent if agent in AGENTS else "claude"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        payload = normalize(payload if isinstance(payload, dict) else {}, agent)
        handler = {"start": start, "end": end, "turn": turn, "prompt": prompt}.get(which)
        return handler(payload, agent) if handler else 0
    except Exception as exc:  # noqa: BLE001  hook 永远不能让会话失败
        print(f"krouter hook: {str(exc)[:200]}", file=sys.stderr)
        return 0
    finally:
        if agent == "cursor" and which in CURSOR_REPLY:
            print(json.dumps(CURSOR_REPLY[which]))


if __name__ == "__main__":
    raise SystemExit(main())
