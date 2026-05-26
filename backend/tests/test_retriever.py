from app.services import retriever


def test_deterministic_embedding_is_stable():
    first = retriever.deterministic_embedding("semiconductor policy shock")
    second = retriever.deterministic_embedding("semiconductor policy shock")
    assert first == second
    assert len(first) == 384


def test_format_memory_document_includes_news_and_forward_return():
    document = retriever.format_memory_document("AI 芯片利好", "半导体指数上涨 2%")
    assert "历史新闻：AI 芯片利好" in document
    assert "后三天走势：半导体指数上涨 2%" in document


def test_retrieve_similar_memories_returns_top_three(tmp_path, monkeypatch):
    class FakeChromaRetriever:
        def __init__(self):
            pass

        def retrieve(self, query, top_k=3):
            assert top_k == 3
            assert "008282" in query
            return [
                {"text": "历史新闻：A\n后三天走势：上涨", "metadata": {}, "distance": 0.1},
                {"text": "历史新闻：B\n后三天走势：下跌", "metadata": {}, "distance": 0.2},
                {"text": "历史新闻：C\n后三天走势：震荡", "metadata": {}, "distance": 0.3},
            ]

    monkeypatch.setattr(retriever, "ChromaRetriever", FakeChromaRetriever)
    snippets = retriever.retrieve_similar_memories(
        {"asset_code": "008282", "market_snapshot": {"vix": 18.5}}, top_k=3
    )
    assert len(snippets) == 3
    assert snippets[0].startswith("历史新闻：A")
