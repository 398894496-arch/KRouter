#!/usr/bin/env python3
"""Nightly: learn how you mention things, from what the agent fetched when the prompt hook said nothing.

The prompt hook (`recollect.py`) brings a page when your message uses a name it knows. When it said nothing and the
agent then fetched a page itself (`krouter_ask`, the route command, or reading the file) and used it in its answer, the
turn hook writes a `learn` event: your sentence (redacted, at most 300 characters) and the page. This step turns each
event into at most `PER_EVENT` phrases from your own words that point at that page and nowhere else, and appends them to
`90 系统文件/自动化/下意识触发词-待验证.psv` (`rel|phrase`): provisional, recall-only trigger words, the same mechanism
as the generated ones, so next time the hook brings the page itself. No model call.

A phrase is kept only when it: is two to four Latin words or three to six Chinese characters, four or more once spaces
and punctuation are dropped (so the hook's own rule lets it count inside a long message); neither starts nor ends on a
function word; holds a word that is not everyday vocabulary (a Chinese two-character word outside the 1,000 most common,
a Latin word that is not a function word, or a number); is not, and does not hold or sit inside, a name or trigger of
another page; and does not occur on two or more other pages of the vault. The longest-scoring phrase wins; ties go to
the shorter.

A `contradict` event (the hook brought a page by one of these provisional phrases, and the agent used a different page
it fetched instead) removes that phrase. Every change is listed in the step's output, and the file says where each
line came from. `--dry-run` writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recollect  # noqa: E402
import recall_index as ri  # noqa: E402
import zones  # noqa: E402

OUT = "90 系统文件/自动化/下意识触发词-待验证.psv"
OFFSET = "recall-learn.offset"
PER_EVENT = 1
FUNCTION_ZH = set("的了着过地得吗呢吧啊么呀嘛我你他她它们是在有和与及就都也还又要会能可把被给让对这那哪个些一不没很太再才")
CLAUSE = re.compile(r"[，。！？；：、,!?;:()（）\[\]「」『』\"'“”‘’<>《》\n]+|\.(?=\s|$)")


def is_cjk(u: str) -> bool:
    return len(u) == 1 and "㐀" <= u <= "鿿"


_RANK: dict[str, int] = {}


def rank(word: str) -> int:
    """A two-character word's place in the bundled frequency list (0 = not a listed word)."""
    if not _RANK:
        f = ri.LEXICON_FILE
        words = [w for w in f.read_text(encoding="utf-8").splitlines() if w and not w.startswith("#")] if f.is_file() else []
        _RANK.update({w: i + 1 for i, w in enumerate(words)})
    return _RANK.get(word, 0)


def word_weight(w: str) -> int:
    """0 for everyday words; more for words that name something."""
    if all(is_cjk(c) for c in w):
        if len(w) < 2 or set(w) & FUNCTION_ZH or w in ri.QUERY_STOP:
            return 0
        r = rank(w) if len(w) == 2 else 0
        if r == 0:  # 词表里没有的词：团队自己的叫法，或分错的边角
            return 2 if set(w) - ri.COMMON_CHARS else 1
        return 0 if r <= ri.GENERIC_WORDS else (2 if r > 6000 else 1)
    low = w.lower()
    if re.search(r"\d", low) and len(re.sub(r"\D", "", low)) >= 2:
        return 2  # 数字：99.5、A100、8 小时
    if len(w) >= 2 and (w.isupper() or re.search(r"[a-z][A-Z]|[-_.+#]", w)):
        return 2  # 缩写、技术记号：DB、fine-tune、gofmt.v2
    return 0 if low in ri.EN_FUNCTION or len(low) < 4 else 1


def segment(run: str) -> list[str]:
    """Greedy two-character segmentation of a Chinese run with the bundled word list. Characters the list does not
    pair up are joined into one unlisted word when two to four of them stand together and none is a function
    character (「灰度」「老库」: team words are often not in a general list); a lone one stays a single character."""
    out, i, loose = [], 0, ""

    def flush():
        nonlocal loose
        if 2 <= len(loose) <= 4 and not set(loose) & FUNCTION_ZH:
            out.append(loose)
        else:
            out.extend(loose)
        loose = ""

    while i < len(run):
        if i + 1 < len(run) and rank(run[i:i + 2]):
            flush()
            out.append(run[i:i + 2])
            i += 2
        elif run[i] in FUNCTION_ZH:
            flush()
            out.append(run[i])
            i += 1
        else:
            loose += run[i]
            i += 1
    flush()
    return out


TOKEN = re.compile(r"[\u3400-\u9fff]+|[A-Za-z0-9][A-Za-z0-9.+#_%-]*")


def candidates(sentence: str) -> list[tuple[str, int]]:
    """(phrase, weight) pairs: two adjacent Chinese words, a technical token with the word next to it, or two or three
    Latin words in a row (not the first word of a sentence when it is capitalised: a person's name, not a topic)."""
    out = []
    for clause in CLAUSE.split(sentence):
        toks = []
        for m in TOKEN.finditer(clause):
            tok = m.group(0)
            if is_cjk(tok[0]):
                toks += [(w, "zh") for w in segment(tok)]
            else:
                toks.append((tok, "en"))
        for i in range(len(toks)):
            for j in (i + 2, i + 3):
                if j > len(toks):
                    continue
                span = toks[i:j]
                words = [w for w, _ in span]
                if any(len(w) == 1 and is_cjk(w) for w in words):
                    continue  # 落单的汉字不进叫法
                if span[0][1] == "en" and (words[0].lower() in ri.EN_FUNCTION or (i == 0 and words[0][:1].isupper()
                                                                                 and not words[0].isupper())):
                    continue
                if span[-1][1] == "en" and words[-1].lower() in ri.EN_FUNCTION:
                    continue
                if all(l == "zh" for _, l in span) and j - i != 2:
                    continue  # 中文只取相邻两个词，像一个叫法
                weight = sum(word_weight(w) for w in words)
                if not all(word_weight(w) for w in words if len(w) > 1) and all(l == "zh" for _, l in span):
                    continue  # 「上周各自」：两个词里有日常词就不像叫法
                text = _join(words)
                if len(recollect.norm(text)) >= 4 and weight >= 2:
                    out.append((text, weight))
    return out


def _join(words: list[str]) -> str:
    s = ""
    for u in words:
        if s and not (is_cjk(u[0]) and is_cjk(s[-1])):
            s += " "
        s += u
    return s


def _vault_texts(vault: Path) -> list[tuple[str, str]]:
    out = []
    for full, rel in ri.walk_md(vault):
        try:
            out.append((zones.canon(vault, rel), recollect.norm(Path(full).read_text(encoding="utf-8", errors="replace"))))
        except OSError:
            continue
    return out


def pick(vault: Path, sentence: str, page: str, texts: list[tuple[str, str]] | None = None,
         taken: list[tuple] | None = None) -> list[str]:
    """At most PER_EVENT phrases from `sentence` that point at `page` and nowhere else."""
    texts = _vault_texts(vault) if texts is None else texts
    taken = recollect.entries(vault) if taken is None else taken
    real = zones.real(vault, page)
    others = [(row[1], row[3]) for row in taken if row[3] not in (real, page)]
    scored = []
    for c, score in dict(candidates(sentence)).items():
        a = recollect.norm(c)
        if any(a == o or a in o or (o in a and len(o) >= 2) for o, _rel in others):
            continue  # 已经是（或含着、或藏在）别的页的名字、触发词里
        elsewhere = sum(1 for rel, txt in texts if rel != page and a in txt)
        if elsewhere >= 2:
            continue
        scored.append((score, -len(a), c))
    scored.sort(reverse=True)
    return [c for _s, _l, c in scored[:PER_EVENT]]


def read_events(state: Path) -> tuple[list[dict], int]:
    log = state / recollect.LEARN_LOG
    try:
        start = int((state / OFFSET).read_text().strip() or 0)
    except (OSError, ValueError):
        start = 0
    try:
        with log.open("rb") as fh:
            fh.seek(0, 2)
            end = fh.tell()
            if start > end:
                start = 0
            fh.seek(start)
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return [], start
    out = []
    for line in data.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out, end


HEADER = ("# 夜间从「钩子没递、宿主自己取了这一页并用上了」学到的说法（learn_mentions.py）。待验证：只参与召回，从不锁定；\n"
          "# 之后宿主越过它递的页去用了别的页，这一行会被删掉。不想要的行直接删。格式 rel|说法\n")


def run(vault: Path, state: Path, dry: bool = False) -> dict:
    events, end = read_events(state)
    out_path = zones.path(vault, OUT)
    lines = out_path.read_text(encoding="utf-8").splitlines() if out_path.is_file() else []
    keep = [ln for ln in lines if ln and not ln.startswith("#")]
    have = {ln for ln in keep}
    added, removed = [], []
    texts = None
    for e in events:
        if e.get("kind") == "contradict":
            rel = zones.real(vault, e.get("page", ""))
            line = f"{rel}|{e.get('phrase', '')}"
            if line in have:
                have.discard(line)
                keep = [ln for ln in keep if ln != line]
                removed.append({"page": e["page"], "phrase": e["phrase"], "instead": e.get("instead", "")})
    for e in events:
        if e.get("kind") != "learn" or not e.get("sentence") or not e.get("page"):
            continue
        texts = _vault_texts(vault) if texts is None else texts
        rel = zones.real(vault, e["page"])
        if recollect.current(vault, rel, date.today()) is None:
            continue
        for phrase in pick(vault, e["sentence"], e["page"], texts):
            line = f"{rel}|{phrase}"
            if line not in have and not any(r["phrase"] == phrase and r["page"] == e["page"] for r in removed):
                have.add(line)
                keep.append(line)
                added.append({"page": e["page"], "phrase": phrase, "from": f"{e.get('agent', '')}:{e.get('session', '')}"})
    if not dry and (added or removed):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(HEADER + "".join(ln + "\n" for ln in keep), encoding="utf-8")
    if not dry:
        try:
            state.mkdir(parents=True, exist_ok=True)
            (state / OFFSET).write_text(str(end))
        except OSError:
            pass
    return {"events": len(events), "added": added, "removed": removed,
            "writes": [OUT] if (added or removed) else []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.vault:
        print("set KROUTER_VAULT", file=sys.stderr)
        return 2
    res = run(Path(a.vault), recollect.state_dir(), a.dry_run)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
