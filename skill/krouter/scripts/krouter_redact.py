#!/usr/bin/env python3
"""Secrets never leave the vault through KRouter: not to a model, not into an agent's context, not into the cache.

Two layers.

By page: a secret page is never sent to a model and never quoted (only its path is shown). A page is secret when
its frontmatter says `secret: true`, when it is the key page (`90 系统文件/自动化/自进化钥匙.md`), or when its file
name or title says what it is (凭据 / 密钥 / 秘钥 / 钥匙 / 口令 / credential / secret / password / api key) — the
last needs no declaration, so a host who never configured anything is still covered.

By content, for everything else: every text KRouter prints, indexes, logs or sends goes through `redact()`, which
replaces with `<redacted>`
- values after key-like labels, in either language and any separator (`DEEPSEEK_API_KEY=…`, `Key: …`, `密钥：…`,
  `凭据 …`, `password = …`, `token: …`), including inside table cells;
- secret query parameters (`?key=…`, `&access_token=…`) and the password in a connection string (`user:…@host`);
- bearer tokens and well-known key shapes (`sk-…`, `ghp_…`, `AKIA…`, `AIza…`, `xox…`, `hf_…`, …);
- and, as the backstop, any unbroken run with a piece of ≥ 16 characters mixing letters and digits (keys without a
  known prefix: Mistral, Together, 智谱, Fireworks, Perplexity, NVIDIA, Cerebras …). Long hashes are masked too; that
  only affects what is printed or sent — source pages are never edited, and receipt SHAs are computed by KRouter.
Placeholders (`YOUR_…`, `CHANGE_ME`, `<…>`) and plain numbers stay readable so a page still explains itself.
"""

from __future__ import annotations

import re

SECRET_PAGES = ("90 系统文件/自动化/自进化钥匙.md",)
SECRET_NAME = re.compile(r"凭据|凭证|密钥|秘钥|私钥|钥匙|口令|credential|secret|password|passwd|api[ _-]?key", re.I)
MARK = "<redacted>"
PLACEHOLDER = re.compile(r"^(?:YOUR_|CHANGE_?ME|REPLACE|TODO|PASTE_|sk-your|x{4,}|<|\.\.\.|…|\*{3,})", re.I)
LABEL = (r"(?:[A-Za-z0-9_]*(?:API[_ -]?KEY|APIKEY|ACCESS[_ -]?KEY|SECRET[_ -]?KEY|PRIVATE[_ -]?KEY|SECRET|TOKEN|PASSWORD|"
         r"PASSWD|CREDENTIALS?)[A-Za-z0-9_]*|\bkey\b|密钥|秘钥|私钥|密码|口令|令牌|凭据|凭证|访问密钥)")
ASSIGN = re.compile(r"(?P<k>" + LABEL + r"[\"'`]?\s*(?:[:=：]|\s)\s*[\"'`]?)(?P<v>[^\s\"'`,;|)）]+)", re.I)
QUERY = re.compile(r"(?P<k>[?&](?:key|api_?key|apikey|token|access_token|secret|password|sig|signature|auth)=)(?P<v>[^&#\s]+)",
                   re.I)
CONN = re.compile(r"(?P<k>\b[a-z][a-z0-9+.-]*://[^:/\s@]+:)(?P<v>[^@\s/]+)(?=@)", re.I)
KNOWN = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-(?:ant-|proj-|or-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|glpat-[A-Za-z0-9_-]{20,}"
    r"|hf_[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|pplx-[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}"
    r"|csk-[A-Za-z0-9]{20,}|fw_[A-Za-z0-9]{16,})")
BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{16,}")
RUN = re.compile(r"(?<![A-Za-z0-9+/=_.~:-])[A-Za-z0-9+/=_.~:-]{16,}(?![A-Za-z0-9+/=_.~:-])")


def _value_is_secret(v: str) -> bool:
    if PLACEHOLDER.match(v) or v == MARK or MARK in v:
        return False
    if re.fullmatch(r"[一-鿿\W]+", v):  # 中文说明、标点（`凭据 页面`）不是值
        return False
    has_alpha, has_digit = re.search(r"[A-Za-z]", v), re.search(r"\d", v)
    # `tokens: 158386`（用量数字）不是密钥；钥匙要么够长，要么字母数字混排
    return (len(v) >= 12 and not v.isdigit()) or (len(v) >= 6 and bool(has_alpha and has_digit))


HEX = re.compile(r"[0-9a-fA-F]+")
SRI = re.compile(r"^(?:sha(?:1|256|384|512))[-:]", re.I)


PATHLIKE = re.compile(r"^(?:/|~/|\./|\.\./|[A-Za-z][A-Za-z0-9+.-]*://)")
FILE_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")


def _high_entropy(run: str) -> bool:
    """A long unbroken piece mixing letters and digits — except pure hex (git commits, SHA digests) and SRI
    integrity strings (`sha512-…`): coding notes are full of those, and masking them loses the note's point.
    Hex keys written with a label (`KEY=…`, `密钥：…`) are still caught by the label rule; unlabeled ones are
    left to the secret-page layer."""
    if SRI.match(run) or HEX.fullmatch(run.replace("-", "")):
        return False
    # 路径和 URL（`/Users/…/2026Q3Report2026Final.csv`、`https://docs…/Install2026Guide`、`s3://…`）照原样留着：
    # 知识库里记的路径和链接是有用的信息；放在路径里的已知密钥形状由 KNOWN 那一层拦
    if PATHLIKE.match(run) or FILE_EXT.search(run):
        return False
    for piece in re.split(r"[-_./]", run):
        if len(piece) >= 16 and len(re.findall(r"[A-Za-z]", piece)) >= 2 and len(re.findall(r"\d", piece)) >= 2:
            return True
    return False


def redact(text: str) -> str:
    if not text:
        return text
    text = CONN.sub(lambda m: m.group("k") + (MARK if not PLACEHOLDER.match(m.group("v")) else m.group("v")), text)
    text = QUERY.sub(lambda m: m.group("k") + (MARK if _value_is_secret(m.group("v")) else m.group("v")), text)
    text = ASSIGN.sub(lambda m: m.group("k") + (MARK if _value_is_secret(m.group("v")) else m.group("v")), text)
    text = KNOWN.sub(MARK, text)
    text = BEARER.sub(r"\1" + MARK, text)
    return RUN.sub(lambda m: MARK if _high_entropy(m.group(0)) else m.group(0), text)


def is_secret_page(canon_rel: str, meta: dict | None = None) -> bool:
    """`canon_rel` is the default-layout path (zones.canon); `meta` the page's frontmatter when known."""
    if canon_rel in SECRET_PAGES:
        return True
    if meta and str(meta.get("secret", "")).strip().lower() in {"true", "yes", "1"}:
        return True
    name = canon_rel.rsplit("/", 1)[-1]
    return bool(SECRET_NAME.search(name) or (meta and SECRET_NAME.search(str(meta.get("title", "")))))


if __name__ == "__main__":  # filter: `… | python3 krouter_redact.py` (the shell router's literal search)
    import sys

    hit = re.compile(r"^(.*?\.md)[:-]\d+[:-]")
    for line in sys.stdin:
        m = hit.match(line)
        if m and is_secret_page(m.group(1).rsplit("/", 1)[-1]):
            continue  # 机密页：只字不引
        sys.stdout.write(redact(line))
