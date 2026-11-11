"""KRouter as a LlamaIndex retriever: the page that answers, as a node with its source, or no node at all.

    from krouter.integrations.llamaindex import KRouterRetriever
    retriever = KRouterRetriever()                      # the installed vault; or vault="/path/to/vault"
    nodes = retriever.retrieve("how do we ship a release?")
    nodes[0].node.text, nodes[0].node.metadata["page"]  # the one-line answer and the page it came from

    # in a query engine, an agent tool, a chat engine: anywhere LlamaIndex takes a retriever
    from llama_index.core.query_engine import RetrieverQueryEngine
    engine = RetrieverQueryEngine.from_args(retriever, llm=...)

When the vault does not know (`recall: none`) the retriever returns no nodes, so the engine has nothing to make an
answer from instead of a weak match. A replaced page is never returned. Needs `llama-index-core`.
"""

from __future__ import annotations

import os

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

import krouter

CONFIDENCE = {"high": 1.0, "medium": 0.7, "low": 0.4}


class KRouterRetriever(BaseRetriever):
    def __init__(self, vault: str | os.PathLike | None = None, route: str = "search", **kwargs) -> None:
        self._vault = vault
        self._route = route
        super().__init__(**kwargs)

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        a = krouter.ask(query_bundle.query_str, route=self._route, vault=self._vault)
        if a.refused or not a.page:
            return []
        score = 1.0 if a.fields.get("canonical_match") == "true" else CONFIDENCE.get(a.confidence, 0.5)
        node = TextNode(text=a.how or a.page, id_=a.page,
                        metadata={"page": a.page, "source": "krouter", "confidence": a.confidence or "locked",
                                  "receipt": a.text})
        node.excluded_llm_metadata_keys = ["receipt"]  # 收据给人看、给日志；不塞进模型的上下文
        node.excluded_embed_metadata_keys = ["receipt"]
        return [NodeWithScore(node=node, score=score)]
