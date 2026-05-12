"""Market data: equity / index / currency snapshots.

Two providers:
- yfinance for global equities, indices, commodities, and most currency
  pairs. Free, no key, scraped from Yahoo Finance.
- SNB (Swiss National Bank) for the official CHF reference rates,
  authoritative source for any CHF cross — overrides yfinance when the
  symbol involves CHF.

The investigator uses this when an anomaly might trace back to a macro
move (e.g. EUR/CHF dropped → import margins shifted).
"""

from __future__ import annotations

import logging
from typing import Any

from biq.tools.external.cache import cached_query

_logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 15  # markets move fast — short cache

# Common symbols the Markt-Radar page surfaces.
DEFAULT_SYMBOLS: list[str] = [
    "^SSMI",  # Swiss Market Index
    "^GDAXI",  # DAX
    "^GSPC",  # S&P 500
    "EURCHF=X",
    "USDCHF=X",
    "GC=F",  # Gold front-month
    "BTC-USD",
]


def market_snapshot(
    symbols: list[str] | None = None,
    *,
    period: str = "1mo",
) -> dict[str, Any]:
    """Latest close + recent trajectory for a list of symbols.

    Args:
        symbols: yfinance tickers (e.g. "^SSMI", "EURCHF=X", "AAPL").
            Defaults to a Swiss-business-relevant curated list.
        period: yfinance period string — "5d" / "1mo" / "3mo" / "1y".

    Returns:
        {
            "period": str,
            "items": [
                {
                    "symbol": "EURCHF=X",
                    "name": "EUR/CHF",
                    "last": 0.94,
                    "change_pct": -1.2,
                    "history": [{date, close}],
                },
                ...
            ],
            "cache": "hit" | "miss",
        }
    """
    syms = symbols or DEFAULT_SYMBOLS
    cache_key = f"market::p={period}::{','.join(sorted(syms))}"

    return cached_query(
        source="market",
        query_key=cache_key,
        ttl_minutes=_DEFAULT_TTL_MINUTES,
        fetch=lambda: _fetch(syms, period),
    )


_FRIENDLY_NAMES: dict[str, str] = {
    "^SSMI": "SMI · Swiss Market",
    "^GDAXI": "DAX · Deutschland",
    "^GSPC": "S&P 500 · USA",
    "EURCHF=X": "EUR / CHF",
    "USDCHF=X": "USD / CHF",
    "GBPCHF=X": "GBP / CHF",
    "GC=F": "Gold (Spot)",
    "CL=F": "Brent-Öl",
    "BTC-USD": "Bitcoin",
}


def _friendly(symbol: str) -> str:
    return _FRIENDLY_NAMES.get(symbol, symbol)


def _fetch(symbols: list[str], period: str) -> dict[str, Any]:
    try:
        import yfinance as yf

        items: list[dict[str, Any]] = []
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period=period, auto_adjust=False)
                if hist is None or hist.empty:
                    continue
                closes = hist["Close"].dropna()
                if closes.empty:
                    continue
                last = float(closes.iloc[-1])
                first = float(closes.iloc[0])
                change_pct = ((last - first) / first) * 100.0 if first != 0 else None

                history = [
                    {"date": idx.strftime("%Y-%m-%d"), "close": float(c)}
                    for idx, c in closes.items()
                ]

                items.append(
                    {
                        "symbol": sym,
                        "name": _friendly(sym),
                        "last": round(last, 4),
                        "change_pct": round(change_pct, 2) if change_pct is not None else None,
                        "history": history,
                    }
                )
            except Exception as exc:
                _logger.warning("yfinance fetch for %s failed: %s", sym, exc)
                continue

        return {"period": period, "items": items}
    except Exception as exc:
        _logger.warning("market fetch failed: %s", exc)
        return {"error": f"market fetch failed: {exc}", "items": []}
