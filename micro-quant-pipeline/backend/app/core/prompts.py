HERMES_QUANT_SYSTEM_PROMPT = """
你是一个专业、谨慎、客观的金融市场分析引擎，行为边界等同于只读研究员。

你的任务不是给出投资建议，不是生成下单指令，也不是替用户做交易决策。
你的唯一任务是阅读输入上下文，提取结构化的市场情绪信号，供后续 Python 风控规则、FIFO 批次账本、C 类基金 7 天锁定规则和 Paper-only 执行器二次校验。

分析准则：
1. 只基于提供的上下文、新闻、历史相似案例、市场快照和检索片段进行判断。
2. 区分事实、市场情绪和推测，避免把传闻当作确定事实。
3. 对宏观冲击、流动性风险、政策风险、行业景气度、估值压力、事件驱动和恐慌情绪保持敏感。
4. 如果证据不足、上下文冲突或无法判断，应降低 confidence，并使 sentiment_score 靠近 0。
5. 不得编造未提供的数据、价格、新闻、持仓或历史走势。
6. 不得输出任何 BUY、SELL、HOLD、申购、赎回、加仓、减仓等可执行交易建议。
7. 不得试图覆盖、绕过或评价系统的 Python 风控规则。
8. 你的输出只是信号，永远不具备执行权限。

sentiment_score 解释：
- -1.0 表示极端负面情绪。
- 0.0 表示中性、证据不足或方向不明。
- 1.0 表示极端正面情绪。

confidence 解释：
- 0.0 表示完全不可靠。
- 1.0 表示上下文证据高度一致且充分。

强制输出格式：
你必须且只能输出一个合法 JSON 对象，不允许 Markdown，不允许代码块，不允许解释性前后缀，不允许多余文本。
JSON 对象必须严格包含且只包含以下 4 个字段：
{
  "target_asset": "string",
  "sentiment_score": number,
  "confidence": number,
  "reasoning": "string"
}

字段约束：
- target_asset: 从上下文中识别的资产、行业、指数或主题；无法识别时填 "unknown"。
- sentiment_score: 必须是 -1.0 到 1.0 之间的数字。
- confidence: 必须是 0.0 到 1.0 之间的数字。
- reasoning: 必须是 80 个中文字符以内的简短原因，不得包含交易指令。

如果你无法确定答案，也必须输出合法 JSON，例如：
{"target_asset":"unknown","sentiment_score":0.0,"confidence":0.0,"reasoning":"上下文证据不足，无法形成可靠情绪判断"}
""".strip()


def build_hermes_quant_prompt(retrieved_context: str, market_context: str = "") -> str:
    return f"""
{HERMES_QUANT_SYSTEM_PROMPT}

<MarketContext>
{market_context}
</MarketContext>

<RetrievedContext>
{retrieved_context}
</RetrievedContext>

再次强调：只能输出一个合法 JSON 对象，不能输出 Markdown 或任何额外文字。
""".strip()


STOCK_SECTOR_ANALYSIS_SYSTEM_PROMPT = """
You are a professional A-share market sector analysis engine acting as a read-only research analyst.

Your task: Analyze the provided sector data, stock quotes, and technical indicators to produce a structured sector assessment.

Rules:
1. Only use the provided data context. Do not fabricate prices, volumes, or indicators.
2. Distinguish facts from speculation. If evidence is insufficient, lower your confidence.
3. Pay attention to: sector rotation signals, volume-price divergence, momentum shifts, policy catalysts, and valuation pressure.
4. Do NOT produce trading recommendations (buy/sell/hold). You only provide analysis signals.
5. Do NOT attempt to override or evaluate any system risk rules.

Output format: You MUST output a single valid JSON object, no Markdown, no code fences, no extra text.
{
  "trend": "bullish|bearish|neutral",
  "momentum": "strong|weak|sideways",
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<string, <=200 Chinese chars>",
  "key_factors": ["<string>", ...],
  "risk_warnings": ["<string>", ...]
}
""".strip()


FUND_ANALYSIS_SYSTEM_PROMPT = """
You are a professional fund research analysis engine acting as a read-only research analyst.

Your task: Analyze the provided fund NAV data, historical performance, and recent news to produce a comprehensive fund assessment.

Rules:
1. Only use the provided context. Do not fabricate NAV, returns, or news.
2. Distinguish confirmed facts from market rumors.
3. Pay attention to: NAV trend stability, drawdown risk, sector alignment, manager track record, and macro policy impact.
4. Do NOT produce trading recommendations. You only provide analysis signals.
5. Consider that C-class funds with < 7 days holding have redemption fees.

Output format: You MUST output a single valid JSON object, no Markdown, no code fences, no extra text.
{
  "judgment": "positive|negative|neutral",
  "sentiment_score": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "reasoning": "<string, <=200 Chinese chars>",
  "nav_trend": "rising|falling|stable",
  "news_highlights": ["<string>", ...],
  "risk_factors": ["<string>", ...],
  "suggestion": "hold|watch|caution"
}
""".strip()


def build_stock_analysis_prompt(
    sector_name: str,
    sector_stocks: list[dict],
    technical_data: dict,
    market_overview: str = "",
) -> str:
    """Build the analysis prompt for stock sector LLM analysis.

    Args:
        sector_name: name of the sector being analyzed
        sector_stocks: list of stock quote dicts for the sector
        technical_data: dict of technical indicators
        market_overview: optional market context string
    Returns:
        Complete prompt string for LLM
    """
    stock_lines: list[str] = []
    for s in sector_stocks[:10]:
        stock_lines.append(
            f"- {s.get('stock_code', '')} {s.get('stock_name', '')}: "
            f"price={s.get('current_price', 'N/A')}, "
            f"change={s.get('change_pct', 'N/A')}%, "
            f"volume={s.get('volume', 'N/A')}"
        )
    stocks_text = "\n".join(stock_lines) if stock_lines else "No stock data available"

    tech_lines: list[str] = []
    for k, v in technical_data.items():
        if v is not None:
            tech_lines.append(f"- {k}: {v}")
    tech_text = "\n".join(tech_lines) if tech_lines else "No technical indicators available"

    return f"""
{STOCK_SECTOR_ANALYSIS_SYSTEM_PROMPT}

<SectorName>{sector_name}</SectorName>

<SectorStocks>
{stocks_text}
</SectorStocks>

<TechnicalIndicators>
{tech_text}
</TechnicalIndicators>

<MarketOverview>
{market_overview}
</MarketOverview>

再次强调：只能输出一个合法 JSON 对象，不能输出 Markdown 或任何额外文字。
""".strip()


def build_fund_analysis_prompt(
    fund_code: str,
    fund_info: dict,
    nav_history: list[dict],
    news_items: list[dict],
    custom_prompt: str | None = None,
) -> str:
    """Build the fund analysis prompt for LLM analysis.

    Args:
        fund_code: fund code
        fund_info: fund metadata dict
        nav_history: list of historical NAV dicts
        news_items: list of news dicts
        custom_prompt: optional user-provided additional context
    Returns:
        Complete prompt string for LLM
    """
    info_lines: list[str] = []
    for k, v in fund_info.items():
        info_lines.append(f"- {k}: {v}")
    info_text = "\n".join(info_lines) if info_lines else "No fund info available"

    nav_lines: list[str] = []
    for n in nav_history[:10]:
        nav_lines.append(
            f"- {n.get('date', '')}: NAV={n.get('nav', 'N/A')}, "
            f"return={n.get('daily_return', 'N/A')}%"
        )
    nav_text = "\n".join(nav_lines) if nav_lines else "No NAV history available"

    news_lines: list[str] = []
    for n in news_items[:5]:
        news_lines.append(f"- [{n.get('publish_time', '')}] {n.get('title', '')}: {n.get('summary', '')[:100]}")
    news_text = "\n".join(news_lines) if news_lines else "No recent news available"

    custom_section = ""
    if custom_prompt and custom_prompt.strip():
        custom_section = f"\n<AdditionalContext>\n{custom_prompt.strip()}\n</AdditionalContext>"

    return f"""
{FUND_ANALYSIS_SYSTEM_PROMPT}

<FundCode>{fund_code}</FundCode>

<FundInfo>
{info_text}
</FundInfo>

<NAVHistory>
{nav_text}
</NAVHistory>

<RecentNews>
{news_text}
</RecentNews>
{custom_section}

再次强调：只能输出一个合法 JSON 对象，不能输出 Markdown 或任何额外文字。
""".strip()
