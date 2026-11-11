"""The knowledge base (kb.py): reference material is found with its source, listed apart, and never counts as what you
decided. With a folder declared, a question only the folder's pages match gets `recall: none` from the memory and a
receipt whose first line is `memory: none`; the confidence comes from the memory alone."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "sdk"))
import kb  # noqa: E402
import recall_index as ri  # noqa: E402

RULES = {
    "Release process": "We ship releases every other Thursday, after the staging deploy has been green for a day.",
    "Database backups": "The database is backed up every night at 03:00 to object storage and kept for 30 days.",
    "Code review": "Every pull request needs one approval; changes over 400 lines are split.",
    "On-call handover": "On-call hands over on Monday at 10:00 in the on-call channel.",
    "Log retention": "Application logs are kept 14 days, audit logs one year.",
    "Package manager": "Frontend repositories use pnpm and commit the lock file.",
    "Payment timeout": "The payment API times out after 8 seconds and retries twice.",
    "Weekly report": "The weekly report goes out on Friday before 17:00.",
    "Expense approval": "Expenses under 5000 are approved by the team lead, above that by finance.",
    "Server size": "Production servers have at least 8 cores and 16 GB of memory.",
    "Error tracking": "Errors are reported to Sentry and alerts go to the alerts channel.",
    "Branch names": "Branch names start with feat/, fix/ or chore/ and the ticket number.",
}
ARTICLE = ("# Billing outage at a fintech\n\nSource: https://example.org/news/billing-outage\n\n"
           "The billing service database ran out of connections during a schema migration. Engineers rotated the "
           "production database credentials and restarted the billing service one server at a time. The postmortem "
           "found the database password stored in plain text in a configuration file.\n")
ARTICLE2 = ("# Token bucket rate limiting\n\nSource: https://example.org/guides/token-bucket\n\nA token bucket gives "
            "each client a bucket that refills at a fixed rate; each request takes a token and a request that finds "
            "the bucket empty is rejected with HTTP 429.\n")
ARTICLE3 = ("# Kubernetes scheduling\n\nSource: https://example.org/k8s\n\nThe scheduler filters nodes that cannot run "
            "a pod, scores the rest and binds the pod to the best node; pods no node can take stay pending.\n")
RESEARCH = "Projects/Billing rewrite/Research"


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_ZONES", raising=False)
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    v = tmp_path / "v"
    _write(v, "krouter-zones.psv", "@lang|en\n")
    for name, text in RULES.items():
        _write(v, f"Rules/{name}.md", f"---\nstatus: active\n---\n# {name}\n\n**{text}**\n")
    _write(v, f"{RESEARCH}/Billing outage at a fintech.md", ARTICLE)
    _write(v, f"{RESEARCH}/Token bucket rate limiting.md", ARTICLE2)
    _write(v, f"{RESEARCH}/Kubernetes scheduling.md", ARTICLE3)
    return v


def _receipt(v: Path, q: str, route: str = "search") -> str:
    env = {**os.environ, "KROUTER_VAULT": str(v), "OBSIDIAN_VAULT": str(v)}
    out = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), route, q], env=env, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


Q_ARTICLE = "How did the billing service outage happen?"


def test_undeclared_research_is_memory_when_automatic_recognition_is_off(vault, monkeypatch):
    monkeypatch.setenv("KROUTER_KB_AUTO", "0")
    res = ri.recall(vault, Q_ARTICLE)
    assert "kb" not in res
    assert res["hits"] and res["hits"][0]["rel"].startswith(RESEARCH)


def test_undeclared_article_is_recognised_without_declaring(vault):
    """2.1.0: nothing declared, the article (long, impersonal, written like an article) is reference material."""
    res = ri.recall(vault, Q_ARTICLE)
    assert res["confidence"] == "none" and not res["hits"]
    assert res["kb"][0]["rel"] == f"{RESEARCH}/Billing outage at a fintech.md" and res["kb"][0]["kb"] == "auto"
    assert res["kb"][0]["signals"]
    text = _receipt(vault, Q_ARTICLE)
    assert text.splitlines()[0].startswith("memory: none")
    assert f"- {RESEARCH}/Billing outage at a fintech.md kb=auto" in text


def test_marking_a_page_mine_wins_over_recognition(vault, capsys):
    page = f"{RESEARCH}/Billing outage at a fintech.md"
    assert kb.main(["--vault", str(vault), "mine", page]) == 0
    assert "marked as yours" in capsys.readouterr().out
    assert "!" + page in (vault / kb.KB_FILE).read_text(encoding="utf-8")
    assert kb.reason(vault, page) == ""
    res = ri.recall(vault, Q_ARTICLE)
    assert "kb" not in res and res["hits"][0]["rel"] == page
    # a declaration of the folder still wins over the score, and add/remove keep the mark
    kb.add(vault, ["Rules"])
    assert "!" + page in (vault / kb.KB_FILE).read_text(encoding="utf-8")
    assert kb.main(["--vault", str(vault), "unmine", page]) == 0
    assert kb.reason(vault, page) == "auto"


def test_own_pages_are_not_recognised(vault):
    for rel in [f"Rules/{n}.md" for n in RULES]:
        assert kb.reason(vault, rel) == ""


def test_declared_folder_only_match_says_memory_none_first(vault):
    assert kb.add(vault, [RESEARCH]) == [RESEARCH]
    res = ri.recall(vault, Q_ARTICLE)
    assert res["confidence"] == "none" and not res["hits"]
    assert [k["rel"] for k in res["kb"]][0] == f"{RESEARCH}/Billing outage at a fintech.md"
    assert res["kb"][0]["kb"] == "declared"
    text = _receipt(vault, Q_ARTICLE)
    assert text.splitlines()[0].startswith("memory: none")
    assert "recall: none" in text
    block = text[text.index("knowledge_base:"):]
    assert f"- {RESEARCH}/Billing outage at a fintech.md kb=declared" in block
    assert "  title: Billing outage at a fintech" in block or "  title: Billing outage" in block
    assert "  L" in block  # 命中的那一行
    # 字面检索的兜底不再把资料页的原文当结果打出来
    tail = text[text.index("recall: none"):text.index("knowledge_base:")]
    assert RESEARCH not in tail


def test_memory_answer_keeps_its_confidence_and_lists_reference_apart(vault):
    q = "How long are audit logs kept?"
    before = ri.recall(vault, q)
    kb.add(vault, [RESEARCH])
    after = ri.recall(vault, q)
    assert after["hits"][0]["rel"] == "Rules/Log retention.md"
    assert after["confidence"] == before["confidence"]
    assert all(not h["rel"].startswith(RESEARCH) for h in after["hits"] + after.get("assoc", []))


def test_reference_never_raises_confidence(vault):
    kb.add(vault, [RESEARCH])
    for q in ("What is a token bucket?", "What does the Kubernetes scheduler do with pending pods?", Q_ARTICLE):
        res = ri.recall(vault, q)
        assert res["confidence"] == "none" and not res["hits"], q
        assert res.get("kb"), q


def test_clipper_frontmatter_counts_without_declaring(vault):
    _write(vault, "Reading/Saved article.md", "---\ntitle: Saved\nsource: https://example.org/a\n---\n# Saved\n\n"
                                              "The zebra migration crosses the river every August, guided by rain.\n")
    res = ri.recall(vault, "When do zebras cross the river?")
    assert res["confidence"] == "none"
    assert res["kb"][0]["rel"] == "Reading/Saved article.md" and res["kb"][0]["kb"] == "clippings"
    assert res["kb"][0]["source"] == "https://example.org/a"


def test_mixed_language_vault_english_question_about_nothing(tmp_path, monkeypatch):
    """A Chinese memory with an English article in a research folder; an English question the memory cannot answer."""
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    v = tmp_path / "zh"
    for i, (name, text) in enumerate({"发版流程": "发版前先跑全量测试，打 tag 后由 CI 发布。",
                                      "数据库备份": "数据库每天凌晨三点备份到对象存储，保留三十天。",
                                      "代码评审": "每个 PR 至少一人批准。", "值班交接": "值班每周一上午交接。",
                                      "日志保留": "审计日志保留一年。", "接口超时": "支付接口超时八秒。"}.items()):
        _write(v, f"02 经验与方法/{name}.md", f"---\nstatus: active\n---\n# {name}\n\n**{text}**\n")
    _write(v, "01 项目/支付重构/调研/Billing outage.md", ARTICLE)
    _write(v, "01 项目/支付重构/调研/Token bucket.md", ARTICLE2)
    q = "What is the production database password of the billing service?"
    kb.add(v, ["01 项目/支付重构/调研"])
    res = ri.recall(v, q)
    assert res["confidence"] == "none" and not res["hits"]
    text = _receipt(v, q)
    assert text.splitlines()[0].startswith("memory: none")  # 中文库：这一行是中文
    assert "你的记忆里没有这件事" in text.splitlines()[0] or "memory has nothing" in text.splitlines()[0]


def test_add_remove_list_and_errors(vault, capsys):
    with pytest.raises(ValueError):
        kb.add(vault, ["No such folder"])
    assert kb.add(vault, [RESEARCH + "/"]) == [RESEARCH]
    assert kb.add(vault, [RESEARCH]) == []
    text = (vault / kb.KB_FILE).read_text(encoding="utf-8")
    assert text.startswith("# Knowledge base") and RESEARCH + "\n" in text
    assert kb.main(["--vault", str(vault), "list"]) == 0
    assert RESEARCH in capsys.readouterr().out
    assert kb.remove(vault, [RESEARCH]) == [RESEARCH] and kb.declared(vault) == []
    assert kb.main(["--vault", str(vault), "add", "nope"]) == 1


def test_suggest_lists_undeclared_reference_and_only_that(vault):
    found = kb.suggest(vault)
    assert [s["folder"] for s in found] == [RESEARCH]
    assert found[0]["url"] == 3
    kb.add(vault, [RESEARCH])
    assert kb.suggest(vault) == []
    assert kb.declared(vault) == [RESEARCH]  # 建议从不自动生效


def test_import_html_with_the_builtin_converter(vault, monkeypatch):
    monkeypatch.setattr(kb.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "markitdown", None)
    src = vault.parent / "page.html"
    src.write_text("<html><head><title>Rate limits</title><style>p{}</style></head><body><h1>Rate limits</h1>"
                   "<p>Use a <b>token bucket</b>; see <a href='https://example.org/x'>the guide</a>.</p>"
                   "<ul><li>429</li><li>Retry-After</li></ul><script>alert(1)</script></body></html>", encoding="utf-8")
    res = kb.import_file(vault, src)
    assert res["tool"] == "builtin-html" and res["folder"] == "Knowledge base" and res["declared"] == ["Knowledge base"]
    page = (vault / res["page"]).read_text(encoding="utf-8")
    assert page.startswith("---\ntitle: \"Rate limits\"\ntype: imported\nsource_file: ")
    assert "imported_at: " in page and "imported_with: builtin-html" in page
    assert "# Rate limits" in page and "**token bucket**" in page and "[the guide](https://example.org/x)" in page
    assert "- 429" in page and "alert(1)" not in page and "p{}" not in page
    assert kb.reason(vault, res["page"]) == "declared"
    again = kb.import_file(vault, src)
    assert again["page"] != res["page"]  # 同名不覆盖


def test_import_without_a_converter_says_what_to_install(vault, monkeypatch):
    monkeypatch.setattr(kb.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "markitdown", None)
    for ext, want in ((".pdf", "pdftotext"), (".docx", "pandoc")):
        src = vault.parent / f"doc{ext}"
        src.write_bytes(b"\x00binary")
        with pytest.raises(kb.ImportFailed) as e:
            kb.import_file(vault, src, RESEARCH)
        assert "markitdown" in str(e.value) and want in str(e.value)
    env = {**os.environ, "KROUTER_VAULT": str(vault), "PATH": str(vault.parent / "empty")}
    out = subprocess.run([sys.executable, "-S", str(SCRIPTS / "kb.py"), "import", str(vault.parent / "doc.pdf")],
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 1 and "Traceback" not in out.stderr and "Install" in out.stderr


def test_prompt_hook_and_standing_index_leave_reference_out(vault, monkeypatch):
    import recollect

    kb.add(vault, [RESEARCH])
    rel = f"{RESEARCH}/Token bucket rate limiting.md"
    assert recollect.current(vault, rel, date.today()) is None
    assert recollect.current(vault, "Rules/Code review.md", date.today()) == ("Rules/Code review.md", "")


def test_sdk_answer_reads_the_block(vault):
    import krouter

    kb.add(vault, [RESEARCH])
    a = krouter.Answer(_receipt(vault, Q_ARTICLE))
    a.fields = krouter._parse(a.text)
    assert a.refused and a.memory_none and a.page == ""
    assert a.references[0]["page"] == f"{RESEARCH}/Billing outage at a fintech.md"
    assert a.references[0]["kb"] == "declared"


def test_why_lists_reference_apart(vault):
    from krouter import why

    kb.add(vault, [RESEARCH])
    e = why.explain(vault, Q_ARTICLE, "en")
    assert e["kb_only"] and e["kb"] and e["verdict"] == "none"
    text = why.render(e)
    assert "In your knowledge base" in text and "only your knowledge base matched" in text.lower()


def test_langgraph_and_scoped_lookups_ignore_the_layer(vault):
    """The LangGraph store asks one scope of its own; a declared knowledge base elsewhere changes nothing there."""
    kb.add(vault, [RESEARCH])
    res = ri.recall(vault, "payment timeout", scope="Rules")
    assert "kb" not in res and res["hits"][0]["rel"] == "Rules/Payment timeout.md"


def test_mcp_server_hands_over_the_block_and_counts_the_refusal(vault, tmp_path):
    """The MCP server (stdio, the same code the team server runs per request) passes the receipt on unchanged: the
    `memory: none` line, the block, and `recall: none`; its instructions and `krouter_ask`'s description explain them."""
    kb.add(vault, [RESEARCH])
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(KROUTER_VAULT=str(vault), OBSIDIAN_VAULT=str(vault), KROUTER_NO_QUERY_LOG="1",
               KROUTER_CACHE_DIR=str(tmp_path / "mcp-cache"))
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "krouter_ask", "arguments": {"query": Q_ARTICLE}}}]
    out = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py")], env=env, capture_output=True, text=True,
                         input="\n".join(json.dumps(m) for m in msgs) + "\n", timeout=120)
    replies = [json.loads(x) for x in out.stdout.splitlines() if x.strip()]
    assert "knowledge_base:" in replies[0]["result"]["instructions"]
    ask_tool = next(t for t in replies[1]["result"]["tools"] if t["name"] == "krouter_ask")
    assert "knowledge_base:" in ask_tool["description"]
    text = replies[2]["result"]["content"][0]["text"]
    assert "memory: none" in text and "knowledge_base:" in text and "recall: none" in text
    assert f"{RESEARCH}/Billing outage at a fintech.md kb=declared" in text


def test_standing_index_lists_memory_topics_only(vault):
    """The session-start index (compile_subconscious) names alias-table topics; a topic whose page is reference
    material is left out once its folder is declared."""
    import compile_subconscious as cs

    _write(vault, "90 系统文件/canonical_sources.psv",
           "# id|aliases|source|anchor\nREVIEW|code review;PR approvals|Rules/Code review.md|one approval\n"
           f"BUCKET|token bucket|{RESEARCH}/Token bucket rate limiting.md|refill rate\n")
    rels = lambda: {t["rel"] for t in cs.index_topics(vault)}  # noqa: E731
    assert rels() == {"Rules/Code review.md", f"{RESEARCH}/Token bucket rate limiting.md"}
    kb.add(vault, [RESEARCH])
    assert rels() == {"Rules/Code review.md"}


def test_nightly_counts_recognised_reference_pages(vault, tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    import nightly

    allp, new = kb.auto_news(vault)
    assert f"{RESEARCH}/Billing outage at a fintech.md" in allp and new == allp
    assert kb.auto_news(vault)[1] == []  # 第二次：没有新认出的
    lines = nightly.kb_lines(vault)
    assert lines and "比上次新增 0 页" in lines[0]
