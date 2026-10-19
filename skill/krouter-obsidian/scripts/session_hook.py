#!/usr/bin/env python3
"""Claude Code hooks: remember a session when it ends, bring this project's decisions when one starts.

The two things that make claude-mem feel like memory, done the KRouter way: what is captured is a plain Markdown
page you can read and fix, and what is brought back is a handful of decisions, each with the page it came from.

`session_hook.py end` (SessionEnd): imports the session that just ended (`import_sessions.py --file`), in the
background so Claude Code is not held up; it also distills that session when you said yes to distilling. Nothing
happens before you said yes to importing (`import_sessions.py --consent`, or the install's question).

`session_hook.py start` (SessionStart): prints, as context for the new session, up to 8 decisions recorded for this
repository (matched by its git top level, never by folder name) in the last 30 days, each naming its page,
corrections first. A decision that a later correction replaced ("原来 A → 改成 B") is left out, so the new session
does not start from the old answer. By default that is every line of pages you confirmed and only the corrections from the rest, marked
unconfirmed; `KROUTER_INJECT=all` brings every line, `KROUTER_INJECT=0` nothing. Nothing is printed when the vault
has none or the import was never turned on. In English unless the lines are Chinese. Reads only the vault; sends
nothing; well under a second.

Both read the hook's JSON on stdin (`session_id`, `transcript_path`, `cwd`) and never fail the session.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zones  # noqa: E402
from krouter_home import project_root, vault_path  # noqa: E402
from krouter_redact import redact  # noqa: E402

DAYS = 30
MAX_LINES = 8
MAX_CHARS = 1600
DIGEST_HEADS = ("## 定了什么、改了什么（模型提炼，待你确认）", "## 现在有效的、被取代的（模型整理，待你确认）")
OLD_SIDE = re.compile(r"^(原来|以前|之前|起初|最初|was|from|before|previously)\s*[:：]?\s*", re.I)
NEW_SIDE = re.compile(r"^(改成|改为|改回|换成|换回|变成|现在|now|back to|to|became)\s*[:：]?\s*", re.I)
TIME = re.compile(r"[（(]\s*(\d{1,2}):(\d{2})\s*[)）]")


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
    decisions. Pages from before 1.0.1 have no `project_root` and are left out until re-imported. From a page you
    confirmed (`status: active`, or `confirmed: true`) every line comes; from an unconfirmed one only corrections
    ("A → B"), unless `KROUTER_INJECT=all`."""
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
    "zh": ("KRouter：这个仓库（{name}）最近 {days} 天在你的库里记下的决定。「→」是改过的；"
           "标「待确认」的是模型提炼、用户还没确认的，只当线索："),
    "en": ("KRouter: decisions recorded in your vault for this repository ({name}) in the last {days} days. "
           "\"→\" marks a change of mind; lines marked (unconfirmed) were extracted by a model and not yet confirmed "
           "by the user, so treat them as clues:"),
}
TAIL = {"zh": "其他问题先用 krouter_ask 查库；库里没有（recall: none）就直说，不要猜。",
        "en": "For anything else, ask the vault with krouter_ask first; if it says recall: none, say so instead of guessing."}
MARK_UNCONFIRMED = {"zh": "（待确认）", "en": " (unconfirmed)"}


def start(payload: dict) -> int:
    mode = os.environ.get("KROUTER_INJECT", "")
    if mode == "0" or not consented():
        return 0
    raw = vault_path()
    if not raw or not Path(raw).is_dir():
        return 0
    root = project_root(payload.get("cwd") or os.getcwd())
    lines = project_lines(Path(raw), root, everything=mode == "all")
    if not lines:
        return 0
    lang = "zh" if any(CJK.search(line) for line, _, _ in lines) else "en"
    body = [HEAD[lang].format(name=Path(root).name, days=DAYS)]
    for line, rel, ok in lines:
        body.append(f"- {line}{'' if ok else MARK_UNCONFIRMED[lang]} 〔{rel}〕")
    body.append(TAIL[lang])
    text = redact("\n".join(body))[:MAX_CHARS]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}},
                     ensure_ascii=False))
    return 0


def end(payload: dict) -> int:
    transcript = payload.get("transcript_path") or ""
    if not transcript or not consented():
        return 0
    raw = vault_path()
    if not raw:
        return 0
    log = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "session-hook.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(HERE / "import_sessions.py"), "--vault", raw, "--file", transcript]
    with log.open("a", encoding="utf-8") as fh:
        kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}  # DETACHED_PROCESS
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
                         env={**os.environ, "OBSIDIAN_VAULT": raw}, **kw)
    return 0


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        return {"start": start, "end": end}.get(which, lambda p: 0)(payload if isinstance(payload, dict) else {})
    except Exception as exc:  # noqa: BLE001  hook 永远不能让会话失败
        print(f"krouter hook: {str(exc)[:200]}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
