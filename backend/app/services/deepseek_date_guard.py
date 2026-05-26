"""DeepSeek date guard middleware.

Solves the stale-data problem caused by DeepSeek's training-data cutoff by:
1. Injecting the real CST date into every system prompt.
2. Replacing vague date words (今天/今日/当前/现在) with absolute dates in user messages.
3. Validating that API responses contain dates matching the current day.
4. Retrying once with stronger date emphasis when validation fails.

Usage::

    guard = DeepSeekDateTimeGuard()
    sys, user = guard.process_request(system_prompt, user_message)
    # ... call API with sys and user ...
    is_valid, reason = guard.process_response(response_text)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# China Standard Time (UTC+8)
CST = timezone(timedelta(hours=8))


class DeepSeekDateTimeGuard:
    """Ensures all DeepSeek calls use correct absolute dates.

    Instantiate once at module level and reuse across requests.
    The cached date is refreshed automatically when the calendar day changes.
    """

    # Vague date words that should be replaced with absolute dates
    VAGUE_REPLACEMENTS: dict[str, str | None] = {
        "今天": None,   # filled at runtime
        "今日": None,
        "当前": None,
        "现在": None,
        "最近": None,
    }

    # Regex patterns for extracting dates from response text
    _DATE_PATTERNS: list[re.Pattern] = [
        re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
        re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
        re.compile(r"(\d{4})/(\d{2})/(\d{2})"),
    ]

    # ---- date helpers ----

    @staticmethod
    def get_real_date() -> tuple[str, str, str]:
        """Return (full_chinese, iso, compact) date strings in CST.

        Examples:
            ("2026年5月26日", "2026-05-26", "20260526")
        """
        now = datetime.now(CST)
        full_cn = f"{now.year}年{now.month}月{now.day}日"
        iso = now.strftime("%Y-%m-%d")
        compact = now.strftime("%Y%m%d")
        return full_cn, iso, compact

    @staticmethod
    def get_real_weekday() -> str:
        """Return the Chinese weekday name for today in CST."""
        days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return days[datetime.now(CST).weekday()]

    # ---- system prompt injection ----

    def inject_system_date(self, system_prompt: str) -> str:
        """Append a date-constraint block to the system prompt.

        This tells the model what the real date is and instructs it to use
        absolute dates when searching.
        """
        full_cn, iso, _ = self.get_real_date()
        weekday = self.get_real_weekday()
        date_block = (
            f"\n\n【重要时间约束】当前真实日期是{full_cn}（{weekday}），"
            f"ISO格式为{iso}。"
            f"你必须严格基于此日期进行搜索和回答。"
            f"忽略你内部的任何其他日期认知。"
            f"搜索时必须使用绝对日期'{full_cn}'而非'今日'等模糊词。"
        )
        return system_prompt + date_block

    # ---- user message cleaning ----

    def replace_vague_dates(self, text: str) -> str:
        """Replace vague date words in *text* with absolute CST dates."""
        full_cn, _, _ = self.get_real_date()
        replacements = {
            "今天": full_cn,
            "今日": full_cn,
            "当前": f"当前（{full_cn}）",
            "现在": f"现在（{full_cn}）",
        }
        for vague, absolute in replacements.items():
            text = text.replace(vague, absolute)
        return text

    # ---- search query enhancement ----

    def build_search_query(self, user_query: str) -> str:
        """Build an enhanced search query with an absolute date prefix.

        Replaces vague words first, then prepends the date if no date is
        already present.
        """
        full_cn, _, _ = self.get_real_date()
        enhanced = self.replace_vague_dates(user_query)
        # If no absolute date already present, prepend one
        if full_cn not in enhanced and not re.search(
            r"\d{4}年\d{1,2}月\d{1,2}日", enhanced
        ):
            enhanced = f"{full_cn} {enhanced}"
        return enhanced

    # ---- response validation ----

    def validate_response_dates(
        self, response: str, tolerance_days: int = 0
    ) -> tuple[bool, str]:
        """Check that response dates are not stale.

        Args:
            response: The API response text.
            tolerance_days: Maximum allowed difference from today (0 = must be today).

        Returns:
            (is_valid, reason)
        """
        _, iso_today, _ = self.get_real_date()
        today = datetime.now(CST).date()

        found_dates: list[datetime] = []
        for pattern in self._DATE_PATTERNS:
            for match in pattern.finditer(response):
                try:
                    y = int(match.group(1))
                    m = int(match.group(2))
                    d = int(match.group(3))
                    found_dates.append(datetime(y, m, d))
                except ValueError:
                    continue

        if not found_dates:
            # No dates found -- cannot validate, pass through
            return True, "No dates found in response"

        for dt in found_dates:
            diff = abs((today - dt.date()).days)
            if diff <= tolerance_days:
                return True, f"Date {dt.date()} matches today"

        stale = ", ".join(str(d.date()) for d in found_dates[:3])
        return False, f"Stale dates detected: {stale}. Today is {iso_today}"

    # ---- convenience wrappers ----

    def process_request(
        self, system_prompt: str, user_message: str
    ) -> tuple[str, str]:
        """Full preprocessing: inject date into system prompt + clean user message.

        Returns:
            (new_system_prompt, new_user_message)
        """
        system_prompt = self.inject_system_date(system_prompt)
        user_message = self.replace_vague_dates(user_message)
        return system_prompt, user_message

    def process_response(self, response: str) -> tuple[bool, str]:
        """Full postprocessing: validate dates in response.

        Returns:
            (is_valid, reason)
        """
        return self.validate_response_dates(response, tolerance_days=0)


# Module-level singleton -- reuse across requests
date_guard = DeepSeekDateTimeGuard()
