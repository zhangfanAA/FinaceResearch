"""Network connectivity diagnostic script for East Money / AkShare endpoints.

Run from the backend directory:
    python test_net.py

Tests:
    Scenario A -- Direct connection (no proxy), with browser-like headers
    Scenario B -- Via local proxy (http://127.0.0.1:7890)
    Scenario C -- AkShare adapter integration test
    Scenario D -- Rapid-fire rate limit test
    Scenario E -- Tenacity retry with exponential backoff
"""

from __future__ import annotations

import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# Step 0: Clear ALL proxy sources BEFORE importing requests
#
# On Windows, `requests` picks up proxy from THREE sources:
#   1. Environment variables (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, ...)
#   2. Windows registry (HKCU\...\Internet Settings\ProxyEnable + ProxyServer)
#      via urllib.request.getproxies_registry()
#   3. macOS system preferences (not relevant here)
#
# We must neutralize ALL three to guarantee direct connection.
# ---------------------------------------------------------------------------
_PROXY_KEYS = (
    "http_proxy", "HTTP_PROXY",
    "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY",
    "no_proxy", "NO_PROXY",
)

print("=" * 70)
print("Network Diagnostics -- East Money / AkShare Proxy & Connectivity Test")
print("=" * 70)

print("\n[Step 0] Clearing ALL proxy sources...")
print("  [0a] Checking proxy environment variables...")
found_proxies = {}
for key in _PROXY_KEYS:
    val = os.environ.get(key)
    if val is not None:
        found_proxies[key] = val

if found_proxies:
    print(f"    WARNING: Found {len(found_proxies)} proxy env var(s):")
    for k, v in found_proxies.items():
        print(f"      {k} = {v!r}")
    for key in _PROXY_KEYS:
        os.environ.pop(key, None)
    print("    Cleared all proxy env vars.")
else:
    print("    OK: No proxy environment variables found.")

# [0b] Override urllib.request.getproxies to ignore Windows registry proxy
import urllib.request

_original_getproxies = urllib.request.getproxies

def _no_registry_proxies():
    """Return empty proxy dict -- ignore Windows registry proxy settings."""
    return {}

urllib.request.getproxies = _no_registry_proxies
print("  [0b] Patched urllib.request.getproxies to ignore Windows registry proxy.")

# [0c] Check Windows registry proxy (informational)
try:
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
        winreg.CloseKey(key)
        if proxy_enable:
            print(f"  [0c] Windows registry proxy is ENABLED: {proxy_server}")
            print("       (Overridden by urllib patch above)")
        else:
            print("  [0c] Windows registry proxy is disabled.")
    except FileNotFoundError:
        print("  [0c] Windows registry proxy keys not found.")
except ImportError:
    print("  [0c] winreg not available (non-Windows platform).")

# Now safe to import requests
import requests

# Test URLs
EASTMONEY_TEST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_PARAMS = {
    "pn": 1,
    "pz": 5,
    "po": 1,
    "np": 1,
    "fltt": 2,
    "invt": 2,
    "fid": "f3",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f2,f3,f12,f14",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

LOCAL_PROXY = "http://127.0.0.1:7890"


def _print_result(label: str, success: bool, status_code: int | str, elapsed_ms: float, detail: str = "") -> None:
    icon = "PASS" if success else "FAIL"
    print(f"\n  [{icon}] {label}")
    print(f"       Status: {status_code}")
    print(f"       Time:   {elapsed_ms:.0f} ms")
    if detail:
        print(f"       Detail: {detail}")


# ---------------------------------------------------------------------------
# Scenario A: Direct connection (no proxy)
# ---------------------------------------------------------------------------
print("\n" + "-" * 70)
print("[Scenario A] Direct connection (proxies forced OFF)")
print("-" * 70)

try:
    t0 = time.monotonic()
    resp = requests.get(
        EASTMONEY_TEST_URL,
        params=EASTMONEY_PARAMS,
        headers=BROWSER_HEADERS,
        proxies={"http": None, "https": None},
        timeout=10,
    )
    elapsed = (time.monotonic() - t0) * 1000
    resp.raise_for_status()
    body = resp.json()
    data_count = len((body.get("data") or {}).get("diff") or [])
    _print_result(
        "East Money push2 (direct, no proxy)",
        success=True,
        status_code=resp.status_code,
        elapsed_ms=elapsed,
        detail=f"Returned {data_count} records",
    )
except requests.exceptions.ProxyError as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (direct, no proxy)",
        success=False,
        status_code="ProxyError",
        elapsed_ms=elapsed,
        detail=f"Proxy still interfering: {exc}",
    )
except requests.exceptions.ConnectionError as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (direct, no proxy)",
        success=False,
        status_code="ConnectionError",
        elapsed_ms=elapsed,
        detail=str(exc)[:200],
    )
except requests.exceptions.Timeout as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (direct, no proxy)",
        success=False,
        status_code="Timeout",
        elapsed_ms=elapsed,
        detail=str(exc)[:200],
    )
except Exception as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (direct, no proxy)",
        success=False,
        status_code=type(exc).__name__,
        elapsed_ms=elapsed,
        detail=str(exc)[:200],
    )


# ---------------------------------------------------------------------------
# Scenario B: Via local proxy
# ---------------------------------------------------------------------------
print("\n" + "-" * 70)
print(f"[Scenario B] Via local proxy ({LOCAL_PROXY})")
print("-" * 70)

try:
    t0 = time.monotonic()
    resp = requests.get(
        EASTMONEY_TEST_URL,
        params=EASTMONEY_PARAMS,
        headers=BROWSER_HEADERS,
        proxies={"http": LOCAL_PROXY, "https": LOCAL_PROXY},
        timeout=10,
    )
    elapsed = (time.monotonic() - t0) * 1000
    resp.raise_for_status()
    body = resp.json()
    data_count = len((body.get("data") or {}).get("diff") or [])
    _print_result(
        "East Money push2 (via local proxy)",
        success=True,
        status_code=resp.status_code,
        elapsed_ms=elapsed,
        detail=f"Returned {data_count} records",
    )
except requests.exceptions.ProxyError as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (via local proxy)",
        success=False,
        status_code="ProxyError",
        elapsed_ms=elapsed,
        detail=f"Proxy at {LOCAL_PROXY} unreachable: {exc}",
    )
except requests.exceptions.ConnectionError as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (via local proxy)",
        success=False,
        status_code="ConnectionError",
        elapsed_ms=elapsed,
        detail=str(exc)[:200],
    )
except Exception as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money push2 (via local proxy)",
        success=False,
        status_code=type(exc).__name__,
        elapsed_ms=elapsed,
        detail=str(exc)[:200],
    )


# ---------------------------------------------------------------------------
# Scenario C: AkShare integration test
# ---------------------------------------------------------------------------
print("\n" + "-" * 70)
print("[Scenario C] AkShare integration test")
print("-" * 70)

try:
    import akshare as ak

    t0 = time.monotonic()
    df = ak.stock_zh_a_spot_em()
    elapsed = (time.monotonic() - t0) * 1000
    if df is not None and not df.empty:
        _print_result(
            "AkShare stock_zh_a_spot_em()",
            success=True,
            status_code="OK",
            elapsed_ms=elapsed,
            detail=f"Returned {len(df)} rows, columns: {list(df.columns[:5])}...",
        )
    else:
        _print_result(
            "AkShare stock_zh_a_spot_em()",
            success=False,
            status_code="Empty",
            elapsed_ms=elapsed,
            detail="Returned None or empty DataFrame",
        )
except Exception as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "AkShare stock_zh_a_spot_em()",
        success=False,
        status_code=type(exc).__name__,
        elapsed_ms=elapsed,
        detail=str(exc)[:300],
    )


# ---------------------------------------------------------------------------
# Scenario D: Rapid-fire rate limit test (5 sequential requests)
# ---------------------------------------------------------------------------
print("\n" + "-" * 70)
print("[Scenario D] Rate limit / 502 resilience test (5 rapid requests)")
print("-" * 70)

success_count = 0
for i in range(5):
    try:
        t0 = time.monotonic()
        resp = requests.get(
            EASTMONEY_TEST_URL,
            params=EASTMONEY_PARAMS,
            headers=BROWSER_HEADERS,
            proxies={"http": None, "https": None},
            timeout=10,
        )
        elapsed = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            success_count += 1
            print(f"  Request {i+1}: OK ({resp.status_code}, {elapsed:.0f}ms)")
        else:
            print(f"  Request {i+1}: HTTP {resp.status_code} ({elapsed:.0f}ms)")
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"  Request {i+1}: {type(exc).__name__} ({elapsed:.0f}ms) -- {str(exc)[:100]}")
    time.sleep(0.5)  # 500ms gap

print(f"\n  Result: {success_count}/5 requests succeeded.")
if success_count == 5:
    print("  [PASS] No rate limiting detected.")
elif success_count >= 3:
    print("  [WARN] Some requests failed -- possible intermittent rate limiting.")
else:
    print("  [FAIL] Most requests failed -- likely blocked or network issue.")


# ---------------------------------------------------------------------------
# Scenario E: Tenacity retry with exponential backoff
# ---------------------------------------------------------------------------
print("\n" + "-" * 70)
print("[Scenario E] Tenacity retry with exponential backoff (max 3 retries)")
print("-" * 70)

try:
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential_jitter,
        RetryCallState,
    )

    def _log_retry(retry_state: RetryCallState) -> None:
        attempt = retry_state.attempt_number
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        wait = retry_state.next_action.sleep if retry_state.next_action else 0
        print(f"  Retry attempt {attempt} after {wait:.1f}s: {exc}")

    @retry(
        retry=retry_if_exception_type((
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        )),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2.0, max=10.0, jitter=1.5),
        before_sleep=_log_retry,
        reraise=True,
    )
    def _retry_request():
        return requests.get(
            EASTMONEY_TEST_URL,
            params=EASTMONEY_PARAMS,
            headers=BROWSER_HEADERS,
            proxies={"http": None, "https": None},
            timeout=10,
        )

    t0 = time.monotonic()
    resp = _retry_request()
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money with tenacity retry",
        success=True,
        status_code=resp.status_code,
        elapsed_ms=elapsed,
        detail=f"Succeeded after retries",
    )
except Exception as exc:
    elapsed = (time.monotonic() - t0) * 1000
    _print_result(
        "East Money with tenacity retry",
        success=False,
        status_code=type(exc).__name__,
        elapsed_ms=elapsed,
        detail=f"All retries exhausted: {str(exc)[:200]}",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("DIAGNOSTIC SUMMARY")
print("=" * 70)
print("""
If Scenario A passes but Scenario B fails:
  -> Your local proxy (7890) is down. Use direct connection.

If Scenario A fails with ProxyError:
  -> Stale proxy env vars are still active. Check:
     - Windows Settings > Network > Proxy
     - System environment variables
     - .bashrc / .zshrc / PowerShell profile
     Run: set HTTP_PROXY=  && set HTTPS_PROXY=

If Scenario A returns 502:
  -> East Money is rate-limiting your IP. Solutions:
     1. Add delays between requests (time.sleep)
     2. Use tenacity exponential backoff (see below)
     3. Rotate User-Agent headers
     4. Reduce request frequency

If Scenario C (AkShare) fails but Scenario A passes:
  -> AkShare internal issue. Check akshare version: pip show akshare
     Try upgrading: pip install --upgrade akshare
""")
print("=" * 70)
