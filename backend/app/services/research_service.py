from __future__ import annotations

from app.config import Config
from app.services.cloud_llm import generate_with_cloud_llm


async def analyze_fund_research(config: Config, prompt: str) -> str:
    return await generate_with_cloud_llm(
        config,
        prompt,
        allow_web_search_tools=True,
    )
