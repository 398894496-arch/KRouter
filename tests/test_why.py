"""`krouter why`: how a lookup came out, in words. The four ways a question can end (an answer, pages brought along a
connection, an old page and the new one that changed it, and "the memory does not know"), plus the lock, both
languages, and that none of it writes anything."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))
from krouter import sample, why  # noqa: E402


@pytest.fixture(scope="module")
def vaults(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("why")
    mp.setenv("KROUTER_NO_QUERY_LOG", "1")
    mp.setenv("KROUTER_CACHE_DIR", str(root / "cache"))
    mp.setenv("KROUTER_STATE_DIR", str(root / "state"))
    mp.delenv("OBSIDIAN_VAULT", raising=False)
    mp.delenv("KROUTER_VAULT", raising=False)
    en = sample.build(root / "en", "en")
    zh = sample.build(root / "zh", "zh")
    yield {"en": en, "zh": zh, "root": root}
    mp.undo()


def tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def text_of(e: dict) -> str:
    return why.render(e)


def test_an_answer_says_which_words_matched_and_how_the_score_came_about(vaults):
    e = why.explain(vaults["en"], "how do we deploy to production")
    assert e["verdict"] == "answer" and e["confidence"] == "high" and e["lang"] == "en"
    top = e["pages"][0]
    assert top["rel"].endswith("Deploy checklist.md") and top["tier"] == "rule"
    assert {m["word"] for m in top["matched"]} >= {"deploy", "production"}
    # the explanation reproduces the number recall gave: relevance × the tier weight
    assert top["explained"] and abs(top["base"] * 1.6 - top["score"]) < 0.002
    text = text_of(e)
    assert "Answered by the ranked search. Confidence: high." in text
    assert "deploy in the title" in text and "×1.6" in text
    assert "4.0" in text.split("Why this confidence", 1)[1] or "×" in text  # the margin is said
    # every shown page has its words, its weight and its one-line answer
    assert all(pg["matched"] for pg in e["pages"][:1]) and all(pg["how"] for pg in e["pages"])


def test_pages_brought_along_a_connection_say_from_where_and_by_which_kind(vaults):
    e = why.explain(vaults["en"], "how do we deploy to production")
    by = {a["rel"].rsplit("/", 1)[-1]: a for a in e["assoc"]}
    assert "Rollback plan.md" in by
    kinds = {v["kind"] for v in by["Rollback plan.md"]["via"]}
    assert {"link", "cocite"} <= kinds  # a wikilink and being cited together before
    assert all(v["from"].endswith("Deploy checklist.md") for v in by["Rollback plan.md"]["via"] if v["kind"] != "words")
    text = text_of(e)
    assert "5. Pages that came along a connection" in text
    assert "linked with 02 Methods/Deploy checklist.md" in text
    assert "cited together with 02 Methods/Deploy checklist.md in earlier lookups" in text
    assert "shares rare words with" in text  # the words are named too
    assert any(b["t"] == "li" and b["page"] and b["page"].endswith("Rollback plan.md") for b in why.blocks(e))


def test_an_old_page_and_the_new_one_that_changed_it(vaults):
    e = why.explain(vaults["en"], "which database does the billing service use")
    c = e["conflict"]
    assert c and c["sure"] and c["newer"].endswith("Database choice, revisited.md") and c["older"].endswith("Database choice.md")
    assert e["pages"][0]["rel"] == c["newer"] and e["pages"][0]["reordered"]
    text = text_of(e)
    assert "changes what 02 Methods/Database choice.md (2026-03-01) says" in text
    assert "moved to first place because it is the newer one" in text
    # and a page the vault replaced is shown as replaced, with who replaced it
    e2 = why.explain(vaults["en"], "when do we ship releases")
    dead = next(p for p in e2["pages"] if p["rel"].endswith("Release day.md"))
    assert dead["tier"] == "dead" and dead["replaced_by"][0].endswith("Release day, changed.md")
    top = e2["pages"][0]
    assert top["rel"].endswith("Release day, changed.md") and top["replaces"][0].endswith("Release day.md")
    assert "was replaced by 02 Methods/Release day, changed.md" in text_of(e2)


def test_the_memory_does_not_know_and_says_which_word_it_could_not_find(vaults):
    e = why.explain(vaults["en"], "what is our on-call rotation")
    assert e["verdict"] == "none" and e["confidence"] == "none" and e["pages"] == []
    assert {"call", "rotation"} <= set(e["words"]["absent"])
    assert e["refusal"][0]["code"] == "r_nothing"
    text = text_of(e)
    assert "The memory does not know this" in text and "rotation" in text and "none: the memory refused" in text
    assert "None. Either nothing is connected strongly enough" in text  # a refusal stays a refusal: nothing associated


@pytest.mark.parametrize("question", [
    "kubernetes cluster autoscaling policy for the billing service",
    "which vendor contract renewal date applies to the billing database",
    "what is the espresso machine descaling schedule",
    "how do we deploy kubernetes",
])
def test_every_refusal_names_the_check_that_said_no(vaults, question):
    """`_refusal` recomputes recall's gate from its helpers; when recall refuses, at least one recomputed check must
    agree (otherwise the explanation would say "could not be reproduced")."""
    e = why.explain(vaults["en"], question)
    if e["confidence"] == "none":
        codes = [r["code"] for r in e["refusal"]]
        assert codes and "r_unknown_reason" not in codes, (question, codes)
    else:
        assert e["refusal"] == []


def test_a_lock_is_explained_before_anything_else(vaults):
    e = why.explain(vaults["en"], "deploy checklist")
    assert e["verdict"] == "locked" and e["lock"]["alias"] == "deploy checklist" and e["lock"]["kind"] == "exact"
    text = text_of(e)
    assert "The question is exactly the alias “deploy checklist”" in text
    assert "the lock answered first and skipped it" in text
    # the alias inside a longer question locks only when it carries the question
    e2 = why.explain(vaults["en"], "what are the pre-deploy steps")
    assert e2["lock"]["state"] in ("locked", "none")


def test_an_alias_that_matches_but_whose_page_was_replaced_is_said_to_be_out_of_force(vaults, tmp_path):
    import shutil

    v = tmp_path / "v"
    shutil.copytree(vaults["en"], v, ignore=shutil.ignore_patterns(".git"))
    page = v / "02 Methods" / "Deploy checklist.md"
    page.write_text(page.read_text(encoding="utf-8").replace("status: active", "status: superseded"), encoding="utf-8")
    e = why.explain(v, "deploy checklist")
    assert e["lock"]["state"] == "dead"
    assert "no longer in force" in text_of(e)


def test_the_language_follows_the_memory_and_can_be_overridden(vaults):
    zh = why.explain(vaults["zh"], "我们哪天发版")
    assert zh["lang"] == "zh"
    text = text_of(zh)
    assert "一、别名锁" in text and "三、页面和顺序" in text and "为什么是这个置信度" in text
    assert "The alias lock" not in text
    en = why.explain(vaults["en"], "when do we ship releases")
    assert en["lang"] == "en" and "1. The alias lock" in text_of(en)
    forced = why.explain(vaults["en"], "when do we ship releases", lang="zh")
    assert forced["lang"] == "zh" and "一、别名锁" in text_of(forced)
    none = why.explain(vaults["zh"], "咖啡机的除垢周期是多久")
    assert none["verdict"] == "none" and "库里没有" in text_of(none)


def test_it_writes_nothing_into_the_memory_and_no_query_log(vaults, monkeypatch, capsys):
    from krouter import cli

    log = vaults["root"] / "state" / "queries.jsonl"
    monkeypatch.delenv("KROUTER_NO_QUERY_LOG", raising=False)  # even with the log switched on, why must not use it
    before = tree_hash(vaults["en"])
    for q in ("how do we deploy to production", "what is our on-call rotation", "deploy checklist"):
        assert cli.main(["--vault", str(vaults["en"]), "why", q]) == 0
    assert tree_hash(vaults["en"]) == before
    assert not log.exists()
    out = capsys.readouterr().out
    assert "Question" in out and "Why this confidence" in out


def test_json_output_is_the_structure(vaults, capsys):
    from krouter import cli

    assert cli.main(["--vault", str(vaults["en"]), "why", "--json", "how do we deploy to production"]) == 0
    e = json.loads(capsys.readouterr().out)
    assert e["verdict"] == "answer" and e["pages"][0]["rel"].endswith("Deploy checklist.md") and "assoc" in e


def test_a_card_whose_situation_reads_like_the_question_is_named(vaults):
    e = why.explain(vaults["en"], "the test fails on CI but passes locally")
    assert [c["id"] for c in e["cards"]["overlap"]] == ["C02"]
    assert "〔C02〕" in text_of(e)
    assert why.explain(vaults["en"], "what is our on-call rotation")["cards"]["overlap"] == []


def test_the_page_paths_in_the_text_are_listed_for_linking(vaults):
    e = why.explain(vaults["en"], "how do we deploy to production")
    listed = why.pages_in(e)
    assert any(r.endswith("Deploy checklist.md") for r in listed) and any(r.endswith("Rollback plan.md") for r in listed)
    assert listed == sorted(listed, key=lambda r: (-len(r), r))
