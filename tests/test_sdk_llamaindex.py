"""KRouter as a LlamaIndex retriever: the answering page as a node with its source; no node when the vault does not
know. Skipped when llama-index-core is not installed."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("llama_index.core")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))
from krouter.integrations.llamaindex import KRouterRetriever  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template", v)
    (v / "02 经验与方法" / "Release day.md").write_text(
        "---\ntitle: Release day\nstatus: active\nhow: Releases go out on Thursday, tagged from main.\n---\n\n"
        "# Release day\n\nReleases go out on Thursday, tagged from main.\n", encoding="utf-8")
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    return v


def test_the_answering_page_comes_back_as_a_node(vault):
    nodes = KRouterRetriever(vault=vault).retrieve("which day do releases go out")
    assert len(nodes) == 1
    node = nodes[0].node
    assert "Thursday" in node.text and node.metadata["page"].endswith("Release day.md")
    assert 0 < nodes[0].score <= 1 and "receipt" in node.excluded_llm_metadata_keys


def test_no_node_when_the_vault_does_not_know(vault):
    assert KRouterRetriever(vault=vault).retrieve("which espresso grinder setting do we use") == []


def test_it_plugs_into_a_query_engine(vault):
    from llama_index.core.llms import MockLLM
    from llama_index.core.query_engine import RetrieverQueryEngine
    from llama_index.core.response_synthesizers import get_response_synthesizer

    from llama_index.core import Settings

    old, Settings.llm = Settings._llm, MockLLM()  # 不调任何模型：只看检索到的来源
    try:
        synth = get_response_synthesizer(llm=MockLLM(), response_mode="no_text")
        engine = RetrieverQueryEngine(retriever=KRouterRetriever(vault=vault), response_synthesizer=synth)
        res = engine.query("which day do releases go out")
    finally:
        Settings._llm = old
    assert res.source_nodes and res.source_nodes[0].node.metadata["page"].endswith("Release day.md")
