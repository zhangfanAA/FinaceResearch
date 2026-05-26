from app.core.prompts import HERMES_QUANT_SYSTEM_PROMPT, build_hermes_quant_prompt


def test_hermes_quant_prompt_requires_strict_json_shape():
    prompt = HERMES_QUANT_SYSTEM_PROMPT
    assert "必须且只能输出一个合法 JSON 对象" in prompt
    assert "target_asset" in prompt
    assert "sentiment_score" in prompt
    assert "confidence" in prompt
    assert "reasoning" in prompt
    assert "不得输出任何 BUY、SELL、HOLD" in prompt
    assert "永远不具备执行权限" in prompt


def test_build_hermes_quant_prompt_includes_contexts():
    prompt = build_hermes_quant_prompt("历史新闻片段", "VIX=18.5")
    assert "历史新闻片段" in prompt
    assert "VIX=18.5" in prompt
    assert "<MarketContext>" in prompt
    assert "<RetrievedContext>" in prompt
