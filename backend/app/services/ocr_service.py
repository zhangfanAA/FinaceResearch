"""OCR / text-parsing service for extracting stock and fund codes from images.

MVP approach:
1. If the caller supplies raw text (extracted from a screenshot via their own OCR),
   we parse 6-digit codes and classify them by heuristic.
2. If the caller supplies a base64-encoded image, we attempt pytesseract OCR;
   if pytesseract is unavailable we fall back to a no-op with an explanatory message.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Stock codes: SH 600/601/603/605/688, SZ 000/001/002/003/300/301
_STOCK_CODE_RE = re.compile(r"\b([0-36]\d{5})\b")
# Fund codes: 6-digit starting with 0-9 (overlaps with stock; heuristic below)
_FUND_CODE_RE = re.compile(r"\b(\d{6})\b")

# Known stock code prefixes (A-share main board + ChiNext + STAR)
_STOCK_PREFIXES = (
    "600", "601", "603", "605",  # SH main
    "688", "689",                 # STAR market
    "000", "001", "002", "003",  # SZ main
    "300", "301",                 # ChiNext
)


def _classify_code(code: str) -> str:
    """Classify a 6-digit code as 'stock' or 'fund' by prefix heuristic."""
    for prefix in _STOCK_PREFIXES:
        if code.startswith(prefix):
            return "stock"
    return "fund"


def parse_text_for_codes(text: str) -> list[dict[str, str]]:
    """Extract 6-digit financial codes from plain text.

    Args:
        text: Plain text potentially containing stock/fund codes.

    Returns:
        List of dicts with keys: ``code``, ``item_type``, ``name`` (always None).
    """
    if not text or not text.strip():
        return []

    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for match in _FUND_CODE_RE.finditer(text):
        code = match.group(1)
        if code in seen:
            continue
        seen.add(code)
        item_type = _classify_code(code)
        results.append({"code": code, "item_type": item_type, "name": None})
    return results


def parse_image_base64(image_base64: str) -> list[dict[str, str]]:
    """Attempt OCR on a base64-encoded image and extract codes.

    Falls back to returning an empty list if pytesseract is not installed
    or the image cannot be decoded.

    Args:
        image_base64: Base64-encoded image string (PNG/JPEG).

    Returns:
        List of dicts with keys: ``code``, ``item_type``, ``name`` (always None).
    """
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception as exc:
        logger.warning("Failed to decode base64 image: %s", exc)
        return []

    try:
        import pytesseract
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return parse_text_for_codes(text)
    except ImportError:
        logger.info(
            "pytesseract not installed; cannot perform image OCR. "
            "Returning empty result."
        )
        return []
    except Exception as exc:
        logger.warning("Image OCR failed: %s", exc)
        return []


def parse_image_or_text(
    image_base64: str | None = None,
    text: str | None = None,
) -> list[dict[str, Any]]:
    """Unified entry-point: try text first, then image OCR.

    Args:
        image_base64: Optional base64-encoded image.
        text: Optional plain text.

    Returns:
        List of dicts with keys: ``code``, ``item_type``, ``name``.
    """
    if text and text.strip():
        return parse_text_for_codes(text)
    if image_base64:
        return parse_image_base64(image_base64)
    return []
