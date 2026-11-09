"""`krouter demo`: decide, change your mind, ask — on a throwaway memory, with no install, no key and no network.

Copies the bundled template to a temporary folder, writes two pages (Monday's decision, Wednesday's correction that
replaces it), asks three questions and prints what came back: the corrected answer with its page, the old page shown
as replaced rather than given as the answer, and a refusal for something the memory never heard of. The folder is
deleted afterwards unless `--keep`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import ask

PAGES = {
    "en": {
        "Release day.md": ("superseded", "2026-11-02", "", "Monday 2026-11-02: we ship a release every Friday afternoon."),
        "Release day, changed.md": ("active", "2026-11-04", "Release day",
                                    "Wednesday 2026-11-04: releases now ship every Tuesday morning, not Friday, "
                                    "because QA runs on Mondays."),
    },
    "zh": {
        "发版日.md": ("superseded", "2026-11-02", "", "周一 2026-11-02：每周五下午发版。"),
        "发版日（改）.md": ("active", "2026-11-04", "发版日", "周三 2026-11-04：发版改到每周二上午，不再周五，因为测试周一才跑完。"),
    },
}
QUESTIONS = {
    "en": ["when do we ship releases", "do we still ship releases on friday", "what is our on-call rotation"],
    "zh": ["我们哪天发版", "还是周五发版吗", "值班表是怎么排的"],
}
SAY = {
    "en": {"head": "KRouter demo: a throwaway memory in {v}",
           "q": "? {q}", "a": "  → {how}\n    from: {page}", "old": "    replaced, shown but not the answer: {page}",
           "no": "  → recall: none. The memory says it does not know instead of guessing.",
           "keep": "Kept: {v} (open it in Obsidian or any editor).", "gone": "Deleted the demo memory. Next: the one-line install in the README."},
    "zh": {"head": "KRouter 演示：临时记忆库在 {v}", "q": "？{q}",
           "a": "  → {how}\n    出处：{page}", "old": "    已被取代，只列出来、不当答案：{page}",
           "no": "  → recall: none。记忆里没有，直说不知道，不拿差不多的凑数。",
           "keep": "保留在：{v}（用 Obsidian 或任何编辑器打开看）。", "gone": "演示用的库已删除。下一步：README 里的一行安装。"},
}


def template_dir(lang: str) -> Path:
    """The template packaged with KRouter, else the repository's own copy."""
    name = "krouter_template_zh" if lang == "zh" else "krouter_template"
    try:
        mod = __import__(name)
        return Path(list(mod.__path__)[0])
    except ImportError:
        return Path(__file__).resolve().parents[2] / ("template-zh" if lang == "zh" else "template")


def build(root: Path, lang: str) -> Path:
    vault = root / "vault"
    shutil.copytree(template_dir(lang), vault)
    rules = vault / "02 经验与方法"
    for name, (status, day, replaces, body) in PAGES[lang].items():
        title = name[:-3]
        fm = f"---\ntitle: {title}\nstatus: {status}\ndate: {day}\n"
        fm += f"supersedes:\n  - \"[[{replaces}]]\"\n" if replaces else ""
        (rules / name).write_text(fm + f"---\n\n# {title}\n\n{body}\n", encoding="utf-8")
    return vault


def run(lang: str = "en", keep: bool = False) -> int:
    lang = "zh" if lang == "zh" else "en"
    say = SAY[lang]
    root = Path(tempfile.mkdtemp(prefix="krouter-demo-"))
    saved = {k: os.environ.get(k) for k in ("KROUTER_NO_QUERY_LOG", "KROUTER_CACHE_DIR", "KROUTER_STATE_DIR")}
    os.environ.update({"KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(root / "cache"),
                       "KROUTER_STATE_DIR": str(root / "state")})  # 演示不碰真的查询日志和缓存
    try:
        vault = build(root, lang)
        print(say["head"].format(v=vault) + "\n")
        bodies = [v[3] for v in PAGES[lang].values()]
        print("  " + bodies[0])
        print("  " + bodies[1] + "\n")
        for q in QUESTIONS[lang]:
            a = ask(q, vault=vault)
            print(say["q"].format(q=q))
            if a.refused or not a.page:
                print(say["no"])
            else:
                print(say["a"].format(how=a.how, page=a.page))
                for h in a.hits:
                    if h["status"] == "superseded":
                        print(say["old"].format(page=h["page"]))
            print()
        print(say["keep"].format(v=vault) if keep else say["gone"])
        return 0
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
