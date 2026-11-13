#!/usr/bin/env python3
"""Page keywords computed with no model (set 45, C1a): the short names a page goes by, for the prompt hook to check a
full-text lookup against. They live in the recall index's `kw` table only; they are not in the full-text columns and change
no ranking, no confidence and no refusal.

A page's keywords: its title and file name, its aliases (frontmatter and the alias table), its headings and bold phrases,
split at separators, and Latin identifiers in its text (`snake_case`, `kebab-case`, `CamelCase`, `ALLCAPS`). Each is
normalised the way the hook normalises a message (`recollect.squash`: case folded, spaces, punctuation and the particles
的了着过地得 dropped), then kept only if it is short enough to be said (Chinese 2–12 characters, Latin 3–40) and is not a
question word or function word. Log pages, superseded or generated pages and secret pages get none.
"""

from __future__ import annotations

import re
import unicodedata

from canonical_lookup import PARTICLES

MAX_PER_PAGE = 40
SPLIT = re.compile(r"[｜|:：/／、，,;；（）()\[\]【】「」\"“”'‘’<>《》—–\-_·]+|\s{2,}|\s+-\s+")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
BOLD = re.compile(r"\*\*([^*\n]{2,40})\*\*")
IDENT = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:[_\-.][A-Za-z0-9]+)+|[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*|[A-Z]{3,}[a-z0-9]*)(?![A-Za-z0-9])")
CJK = re.compile(r"[㐀-鿿豈-﫿]")


def norm(text: str) -> str:
    """`recollect.squash`'s string, without the position maps."""
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(ch.lower() for ch in text
                   if not (ch in PARTICLES or ch.isspace() or unicodedata.category(ch).startswith(("P", "S"))))


def usable(t: str, stop: set[str], function: set[str], function_chars: set[str]) -> bool:
    if CJK.search(t):
        if not 2 <= len(t) <= 12 or t in stop or all(c in function_chars for c in t):
            return False
        return True
    if not t.isascii() or not 3 <= len(t) <= 40 or t.isdigit() or t in function:
        return False
    return True


def keywords(title: str, stem: str, meta: dict, body: str, aliases: list[str], stop: set[str], function: set[str],
             function_chars: set[str]) -> list[tuple[str, str]]:
    """[(normalised term, kind)] for one page, at most MAX_PER_PAGE, the first kind a term came by."""
    raw: list[tuple[str, str]] = []
    for kind, values in (("title", [title]), ("file", [stem]),
                         ("alias", [meta.get("aliases") or "", meta.get("triggers") or ""] + list(aliases)),
                         ("head", HEADING.findall(body)), ("bold", BOLD.findall(body))):
        for v in values:
            whole = v.strip()
            raw.append((whole, kind))
            raw.extend((part, kind) for part in SPLIT.split(whole) if part and part != whole)
    raw.extend((m, "ident") for m in IDENT.findall(body))
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value, kind in raw:
        t = norm(value)
        if t in seen or not usable(t, stop, function, function_chars):
            continue
        seen.add(t)
        out.append((t, kind))
        if len(out) >= MAX_PER_PAGE:
            break
    return out
