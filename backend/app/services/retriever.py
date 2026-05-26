from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


DEFAULT_COLLECTION_NAME = "financial_memory"
DEFAULT_CHROMA_PATH = Path(__file__).resolve().parents[2] / "chroma_data"


def deterministic_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = text.lower().split()
    if not tokens:
        tokens = [text.lower() or "empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class ChromaRetriever:
    def __init__(
        self,
        path: str | Path = DEFAULT_CHROMA_PATH,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        import chromadb

        self.path = Path(path)
        self.client = chromadb.PersistentClient(path=str(self.path))
        self.collection = self.client.get_or_create_collection(collection_name)

    def add_memory(
        self,
        document_id: str,
        news_text: str,
        forward_return_3d: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        document = format_memory_document(news_text, forward_return_3d)
        self.collection.upsert(
            ids=[document_id],
            documents=[document],
            embeddings=[deterministic_embedding(document)],
            metadatas=[metadata or {}],
        )

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[deterministic_embedding(query)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        snippets = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            snippets.append(
                {
                    "text": document,
                    "metadata": metadata or {},
                    "distance": distance,
                }
            )
        return snippets


def format_memory_document(news_text: str, forward_return_3d: str) -> str:
    return f"历史新闻：{news_text}\n后三天走势：{forward_return_3d}"


def build_query_from_state(state: dict[str, Any]) -> str:
    asset_code = state.get("asset_code", "unknown")
    market_snapshot = state.get("market_snapshot", {})
    vix = market_snapshot.get("vix")
    return f"资产：{asset_code}\n当前VIX：{vix}\n请检索相似历史新闻及后三天走势。"


def retrieve_similar_memories(state: dict[str, Any], top_k: int = 3) -> list[str]:
    retriever = ChromaRetriever()
    query = build_query_from_state(state)
    snippets = retriever.retrieve(query, top_k=top_k)
    return [snippet["text"] for snippet in snippets]
