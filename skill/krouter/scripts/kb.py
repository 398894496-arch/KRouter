#!/usr/bin/env python3
"""The knowledge base: reference material in the memory folder, kept apart from what you decided.

A memory folder holds two kinds of page. **Your memory** is what you decided, your rules and corrections, and what
sessions were distilled into. **The knowledge base** is reference material: articles, web clippings, research notes,
documents someone else wrote. Both are indexed and both are found with their source, but a knowledge-base page is never
evidence of what you decided: a lookup lists it in a block of its own, and only your memory sets the confidence.

A page is in the knowledge base when

- a folder on its path is declared in `krouter-kb.txt` at the root of the memory folder (one folder per line, relative
  to the memory folder, `#` for comments; it travels with the memory folder, and a person can read and edit it), or
- a folder on its path is named for clippings (`剪藏`, `Clippings`, `Web clips`), or its frontmatter is a web
  clipper's (a `source:` URL, a `clippings` tag, `type: clipping`). These were treated as clippings before the
  knowledge base existed and need no declaration. (A folder named exactly `Clippings` is not indexed at all.)

    kb.py list                       # the declared folders, and the pages each holds
    kb.py add Research "03 资料"      # declare folders (they must exist)
    kb.py remove Research
    kb.py suggest                    # folders that look like reference material and are not declared (a suggestion only)
    kb.py import report.pdf [--to Research] [--force]   # PDF, Word, HTML, … to a Markdown page in the knowledge base

`suggest` never declares anything; `krouter doctor` shows its findings. `import` converts with a tool already on this
machine (`markitdown`, `pandoc`, or `pdftotext` for PDF); HTML falls back to a plain converter in the standard
library. Nothing is installed for you: when no tool can read the file, it says which one to install.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones  # noqa: E402

KB_FILE = "krouter-kb.txt"
# 剪藏识别（2.0 起）：文件夹名，或网页剪藏插件写的 frontmatter。它们自动算知识库，不用声明
CLIP_PATH = re.compile(r"(^|/)[^/]*(剪藏|clippings?|web ?clips?)[^/]*/", re.I)
CLIP_FM = re.compile(r"^source:\s*[\"']?https?://|^type:\s*[\"']?(web[- ]?)?clip|^tags:.*\bclippings?\b|^\s*-\s*clippings?\s*$",
                     re.M)
DEFAULT_FOLDER = {"zh": "知识库", "en": "Knowledge base"}
HEADER = {
    "zh": ("# 知识库：这里列出的文件夹里是参考资料（文章、剪藏、研究材料、文档）。\n"
           "# 它们照样被索引、能查到、带出处，但不算「你定过的事」：回执把它们单列在 knowledge_base 下，置信度只看你的记忆。\n"
           "# 一行一个文件夹，相对于记忆文件夹；# 开头是注释。改它用 `krouter kb add/remove`，或者直接编辑。\n"),
    "en": ("# Knowledge base: the folders listed here hold reference material (articles, clippings, research, documents).\n"
           "# They are indexed and found with their source, but never count as something you decided: a lookup lists\n"
           "# them under knowledge_base, and only your memory sets the confidence.\n"
           "# One folder per line, relative to the memory folder; lines starting with # are comments. Edit it with\n"
           "# `krouter kb add/remove`, or by hand.\n"),
}
_CACHE: dict[str, tuple[float, list[str]]] = {}


def kb_file(vault: Path) -> Path:
    return Path(vault) / KB_FILE


def _norm(folder: str) -> str:
    return str(folder).strip().replace("\\", "/").strip("/")


def declared(vault: Path | None) -> list[str]:
    """The declared knowledge-base folders (vault-relative, `/`-separated), as the file lists them. Cached per mtime."""
    if vault is None:
        return []
    path = kb_file(vault)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    key = str(path)
    if key in _CACHE and _CACHE[key][0] == mtime:
        return _CACHE[key][1]
    out: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = _norm(line)
        if f and f not in out and not f.startswith("..") and not Path(f).is_absolute():
            out.append(f)
    _CACHE[key] = (mtime, out)
    return out


def path_reason(vault: Path | None, rel: str, folders: list[str] | None = None) -> str:
    """`declared` or `clippings` when the path alone puts the page in the knowledge base, else ``."""
    rel = rel.replace("\\", "/")
    for f in declared(vault) if folders is None else folders:
        if rel == f or rel.startswith(f + "/"):
            return "declared"
    return "clippings" if CLIP_PATH.search(rel) else ""


def fm_reason(fm_text: str) -> str:
    return "clippings" if CLIP_FM.search(fm_text or "") else ""


def head_of(text: str) -> str:
    """The frontmatter block of a page (lowercased, as the index's `fm` table stores it), or ``."""
    text = (text or "").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    return text[: end + 4].lower() if end >= 0 else ""


def reason(vault: Path, rel: str, text: str | None = None) -> str:
    """Why this page is in the knowledge base (`declared`, `clippings`), or `` when it is part of your memory.
    `text`: the page's text when the caller has it; otherwise the page is read."""
    why = path_reason(vault, rel)
    if why:
        return why
    if text is None:
        try:
            text = (Path(vault) / rel).read_text(encoding="utf-8", errors="replace")[:8000]
        except OSError:
            return ""
    return fm_reason(head_of(text))


def classify(con, vault: Path, rels: list[str]) -> dict[str, str]:
    """{rel: reason} for the knowledge-base pages among `rels`, from the paths and the index's stored frontmatter."""
    folders = declared(vault)
    out = {}
    rest = []
    for rel in dict.fromkeys(rels):
        why = path_reason(vault, rel, folders)
        if why:
            out[rel] = why
        else:
            rest.append(rel)
    for i in range(0, len(rest), 400):
        chunk = rest[i:i + 400]
        marks = ",".join("?" * len(chunk))
        for rel, text in con.execute(f"SELECT rel, text FROM fm WHERE rel IN ({marks})", chunk):
            if fm_reason(text):
                out[rel] = "clippings"
    return out


# ---------- 声明 ----------

def _write(vault: Path, folders: list[str]) -> Path:
    path = kb_file(vault)
    lang = "en" if zones.lang(vault) == "en" else "zh"
    keep_head = []
    if path.is_file():
        keep_head = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.startswith("#")]
    head = "\n".join(keep_head) + "\n" if keep_head else HEADER[lang]
    path.write_text(head + "".join(f + "\n" for f in folders), encoding="utf-8")
    _CACHE.pop(str(path), None)
    return path


def add(vault: Path, folders: list[str]) -> list[str]:
    """Declare these folders (each must exist in the memory folder). Returns the ones newly added."""
    have = declared(vault)
    new = []
    for raw in folders:
        f = _norm(raw)
        p = Path(raw).expanduser()
        if p.is_absolute():
            try:
                f = _norm(p.resolve().relative_to(Path(vault).resolve()).as_posix())
            except ValueError:
                raise ValueError(f"{raw} is not inside the memory folder {vault}")
        if not f or f.startswith(".."):
            raise ValueError(f"{raw}: give a folder inside the memory folder")
        if not (Path(vault) / f).is_dir():
            raise ValueError(f"{f}: no such folder in {vault}")
        if f not in have and f not in new:
            new.append(f)
    if new:
        _write(vault, have + new)
    return new


def remove(vault: Path, folders: list[str]) -> list[str]:
    have = declared(vault)
    gone = [f for f in (_norm(x) for x in folders) if f in have]
    if gone:
        _write(vault, [f for f in have if f not in gone])
    return gone


# ---------- 建议（只建议，不生效） ----------

URL_RE = re.compile(r"https?://\S+")
OWN_FM = re.compile(r"^(status|how|supersedes|superseded_by|valid_from|aliases|triggers):|^type:\s*[\"']?(session-excerpt|"
                    r"decision|correction|method|rule|topic|experience|skill|log|daily)", re.M | re.I)
SOURCE_FM = re.compile(r"^(source|url|link|original|origin|来源|原文|原文链接|source_url|source_file):\s*\S", re.M | re.I)
SUGGEST_MIN_PAGES = 3
SUGGEST_SKIP = ("90 系统文件", "05 时间日志", "02 经验与方法/经验卡", "02 经验与方法/技能", "02 经验与方法/主题档案")
LONG_CHARS = 4000


def _page_signals(full: str) -> dict:
    try:
        with open(full, encoding="utf-8", errors="replace") as fh:
            text = fh.read(LONG_CHARS + 4000)  # 判断「长」只要读到这么多
    except OSError:
        return {}
    head = head_of(text)
    body = text[len(head):] if head else text
    first = [ln for ln in body.splitlines() if ln.strip()][:6]
    stem = Path(full).stem
    words = len(re.findall(r"[A-Za-z]+", stem)) + len(re.findall(r"[㐀-鿿]", stem)) / 2
    return {
        "url": bool(SOURCE_FM.search(head) and URL_RE.search(head)) or any(URL_RE.search(ln) for ln in first),
        "long": len(body) >= LONG_CHARS,
        "article": words >= 6 or "author:" in head,
        "own": bool(OWN_FM.search(head)),
    }


def suggest(vault: Path, limit: int = 8) -> list[dict]:
    """Folders that look like reference material someone else wrote and are not in the knowledge base yet. Conservative
    on purpose: at least three pages, few with KRouter's own markers (status, how, a decision or session type), and
    most with a source address at the top, or most long and titled like articles. A suggestion only: nothing changes
    until you declare the folder. Returns [{folder, pages, url, long, article}], largest first."""
    vault = Path(vault)
    folders = declared(vault)
    skip = tuple(zones.real(vault, s) for s in SUGGEST_SKIP)
    stats: dict[str, dict] = {}
    base = str(vault).rstrip("/")
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "迁移备份", "Clippings")]
        reldir = root[len(base) + 1:].replace(os.sep, "/")
        if not reldir or reldir.startswith(skip) or path_reason(vault, reldir + "/x.md", folders):
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            sig = _page_signals(f"{root}/{name}")
            if not sig:
                continue
            parts = reldir.split("/")
            for i in range(1, len(parts) + 1):  # 每一级上层文件夹都累加：整个子树一起看
                s = stats.setdefault("/".join(parts[:i]), {"pages": 0, "url": 0, "long": 0, "article": 0, "own": 0})
                s["pages"] += 1
                for k in ("url", "long", "article", "own"):
                    s[k] += sig[k]

    def looks(s: dict) -> bool:
        n = s["pages"]
        if n < SUGGEST_MIN_PAGES or s["own"] > 0.2 * n:
            return False
        return s["url"] >= 0.6 * n or (s["long"] >= 0.6 * n and s["article"] >= 0.5 * n)

    hit = sorted(f for f, s in stats.items() if looks(s))
    # 上层文件夹只比某个子文件夹多出同样像资料的页时才列上层；一页不多（`Projects` 下只有 `Research`）就列子文件夹
    hit = [f for f in hit if not any(o.startswith(f + "/") and stats[o]["pages"] == stats[f]["pages"] for o in hit)]
    top = [f for f in hit if not any(f.startswith(o + "/") for o in hit if o != f)]  # 上层已经算上就不再列子文件夹
    out = [{"folder": f, **{k: stats[f][k] for k in ("pages", "url", "long", "article")}} for f in top]
    out.sort(key=lambda d: (-d["pages"], d["folder"]))
    return out[:limit]


# ---------- 导入 ----------

class _HTML(HTMLParser):
    """A plain HTML → Markdown conversion: headings, paragraphs, lists, links, code blocks; scripts and styles dropped."""

    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "blockquote", "table", "tr", "ul", "ol",
             "figure", "figcaption", "aside", "nav", "form", "dl"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.title = ""
        self._in_title = False
        self.href: list[str] = []
        self.link_text: list[list[str]] = []

    def _nl(self, n: int = 2) -> None:
        tail = "".join(self.out[-3:])
        have = len(tail) - len(tail.rstrip("\n"))
        if self.out:
            self.out.append("\n" * max(0, n - have))

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._nl()
            self.out.append("#" * int(tag[1]) + " ")
        elif tag in self.BLOCK:
            self._nl()
        elif tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self._nl(1)
            self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag == "pre":
            self._nl()
            self.out.append("```\n")
            self.pre += 1
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "a":
            self.href.append(dict(attrs).get("href") or "")
            self.link_text.append([])
            self.out.append("\x00")  # 链接文字的起点，结束标签时替换

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK:
            self._nl()
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```")
            self._nl()
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "a" and self.href:
            href = self.href.pop()
            self.link_text.pop()
            i = len(self.out) - 1 - self.out[::-1].index("\x00") if "\x00" in self.out else len(self.out)
            text = "".join(self.out[i + 1:]).strip()
            del self.out[i:]
            ok = href and not href.startswith(("#", "javascript:"))
            self.out.append(f"[{text}]({href})" if ok and text else text)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))

    def markdown(self) -> str:
        text = "".join(x for x in self.out if x != "\x00")
        lines = [ln.rstrip() for ln in text.splitlines()]
        text = "\n".join(ln.lstrip() if not ln.startswith("    ") else ln for ln in lines)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def html_to_markdown(text: str) -> tuple[str, str]:
    """(markdown, title) from HTML, with the standard library only."""
    p = _HTML()
    p.feed(text)
    p.close()
    return p.markdown(), html.unescape(p.title).strip()


PANDOC_IN = {".docx": "docx", ".odt": "odt", ".rtf": "rtf", ".epub": "epub", ".html": "html", ".htm": "html",
             ".tex": "latex", ".rst": "rst", ".org": "org"}
TEXT_IN = {".md", ".markdown", ".txt"}


class ImportFailed(Exception):
    pass


def _run(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout.strip() else None


def convert(src: Path) -> tuple[str, str, str]:
    """(markdown, title, tool) for one file, with whatever converter this machine has. Raises ImportFailed with the
    tool to install when none can read it."""
    ext = src.suffix.lower()
    if ext in TEXT_IN:
        return src.read_text(encoding="utf-8", errors="replace"), "", "copy"
    tried = []
    mid = shutil.which("markitdown")
    if mid:
        tried.append("markitdown")
        out = _run([mid, str(src)])
        if out:
            return out, "", "markitdown"
    try:
        from markitdown import MarkItDown  # type: ignore

        tried.append("markitdown (python)")
        res = MarkItDown().convert(str(src))
        text = getattr(res, "text_content", "") or getattr(res, "markdown", "")
        if text.strip():
            return text, getattr(res, "title", "") or "", "markitdown"
    except Exception:  # noqa: BLE001 - 没装或读不了：试下一个
        pass
    pandoc = shutil.which("pandoc")
    if pandoc and ext in PANDOC_IN:
        tried.append("pandoc")
        out = _run([pandoc, "-f", PANDOC_IN[ext], "-t", "gfm", "--wrap=none", str(src)])
        if out:
            return out, "", "pandoc"
    if ext == ".pdf" and shutil.which("pdftotext"):
        tried.append("pdftotext")
        out = _run([shutil.which("pdftotext"), "-layout", "-enc", "UTF-8", str(src), "-"])
        if out:
            return out, "", "pdftotext"
    if ext in (".html", ".htm", ".xhtml"):
        md, title = html_to_markdown(src.read_text(encoding="utf-8", errors="replace"))
        if md.strip():
            return md, title, "builtin-html"
    if ext == ".pdf":
        need = "markitdown (`pipx install 'markitdown[pdf]'`) or pdftotext (poppler: `brew install poppler`, `apt install poppler-utils`)"
    elif ext in PANDOC_IN:
        need = "markitdown (`pipx install 'markitdown[all]'`) or pandoc (https://pandoc.org/installing.html)"
    else:
        need = "markitdown (`pipx install 'markitdown[all]'`), which reads most document formats"
    did = f" (tried: {', '.join(tried)})" if tried else ""
    raise ImportFailed(f"cannot convert {src.name} on this machine{did}. Install {need}, then run this again. "
                       "KRouter does not convert documents itself, apart from plain HTML.")


def _title_of(md: str, fallback: str) -> str:
    for line in md.splitlines()[:40]:
        m = re.match(r"^#\s+(.+?)\s*#*$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def import_file(vault: Path, src: Path, folder: str | None = None, force: bool = False) -> dict:
    """Convert `src` to a Markdown page in the knowledge base. `folder`: where (declared if it was not); default the
    one declared folder, else `知识库` / `Knowledge base` at the root, which is then declared. The page's frontmatter
    keeps the source file's path, the time of the import and the tool. Returns {page, folder, tool, declared}."""
    vault = Path(vault)
    src = Path(src).expanduser()
    if not src.is_file():
        raise ImportFailed(f"no such file: {src}")
    have = declared(vault)
    if folder:
        target = _norm(folder)
    elif len(have) == 1:
        target = have[0]
    elif have:
        raise ImportFailed("more than one knowledge-base folder is declared; say which with --to: " + ", ".join(have))
    else:
        target = DEFAULT_FOLDER["en" if zones.lang(vault) == "en" else "zh"]
    md, title, tool = convert(src)
    if src.suffix.lower() in TEXT_IN and md.startswith("---\n"):
        end = md.find("\n---", 4)
        md = md[end + 4:].lstrip("-\n") if end >= 0 else md  # 原来的 frontmatter 换成导入记录
    title = (title or _title_of(md, src.stem)).strip() or src.stem
    (vault / target).mkdir(parents=True, exist_ok=True)
    newly = [] if path_reason(vault, target + "/x.md") == "declared" else add(vault, [target])
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", src.stem).strip() or "imported"
    page = vault / target / f"{name}.md"
    n = 2
    while page.exists() and not force:
        page = vault / target / f"{name} ({n}).md"
        n += 1
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    head = ["---", f"title: {_yaml(title)}", "type: imported", f"source_file: {_yaml(str(src.resolve()))}",
            f"imported_at: {stamp}", f"imported_with: {tool}", "---", ""]
    page.write_text("\n".join(head) + md.rstrip() + "\n", encoding="utf-8")
    return {"page": page.relative_to(vault).as_posix(), "folder": target, "tool": tool, "declared": newly}


# ---------- 命令行 ----------

def _vault(arg: str | None) -> Path | None:
    import krouter_home

    raw = arg or krouter_home.vault_path()
    return Path(raw).expanduser() if raw else None


def count_pages(vault: Path, folder: str) -> int:
    root = Path(vault) / folder
    return sum(1 for p in root.rglob("*.md")) if root.is_dir() else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="krouter kb", description="Declare reference folders as the knowledge base, "
                                 "see suggestions, import documents.")
    ap.add_argument("--vault", default=None, help="the memory folder (default: the installed one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the declared folders")
    a = sub.add_parser("add", help="declare folders as the knowledge base")
    a.add_argument("folders", nargs="+")
    r = sub.add_parser("remove", help="stop treating folders as the knowledge base")
    r.add_argument("folders", nargs="+")
    sub.add_parser("suggest", help="folders that look like reference material and are not declared (nothing changes)")
    i = sub.add_parser("import", help="convert a PDF, Word, HTML, … file into a Markdown page in the knowledge base")
    i.add_argument("files", nargs="+")
    i.add_argument("--to", default=None, help="the knowledge-base folder (default: the declared one, or a new "
                                              "`知识库` / `Knowledge base`)")
    i.add_argument("--force", action="store_true", help="overwrite a page of the same name")
    args = ap.parse_args(argv)
    vault = _vault(args.vault)
    if vault is None or not vault.is_dir():
        print("set KROUTER_VAULT to your memory folder, or pass --vault", file=sys.stderr)
        return 2
    try:
        if args.cmd == "list":
            folders = declared(vault)
            if not folders:
                print(f"no folder is declared as the knowledge base ({kb_file(vault)} is missing or empty). Clipping "
                      "folders and clipper pages count without it. `krouter kb suggest` lists candidates.")
            for f in folders:
                print(f"{f}\t{count_pages(vault, f)} pages")
        elif args.cmd == "add":
            new = add(vault, args.folders)
            for f in new:
                print(f"declared: {f} ({count_pages(vault, f)} pages) -> {kb_file(vault)}")
            if not new:
                print("already declared: " + ", ".join(_norm(f) for f in args.folders))
        elif args.cmd == "remove":
            gone = remove(vault, args.folders)
            print(("removed: " + ", ".join(gone)) if gone else "none of these is declared")
        elif args.cmd == "suggest":
            found = suggest(vault)
            if not found:
                print("no undeclared folder looks like reference material")
            for s in found:
                print(f"{s['folder']}\t{s['pages']} pages: {s['url']} with a source address, {s['long']} long, "
                      f"{s['article']} titled like articles -> krouter kb add {shlex_quote(s['folder'])}")
        else:
            for f in args.files:
                res = import_file(vault, Path(f), args.to, args.force)
                extra = f"; declared {res['folder']} as the knowledge base" if res["declared"] else ""
                print(f"imported: {f} -> {res['page']} (with {res['tool']}{extra})")
    except (ValueError, ImportFailed) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


if __name__ == "__main__":
    raise SystemExit(main())
