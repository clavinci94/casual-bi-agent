"""External-intelligence tools: web search, news, trends, market data.

Each module exposes one public function (e.g. `web_search()`) that returns
a normalised dict the agent can consume. Results are cached in
`raw.external_signals` with per-source TTLs so identical queries within
the cache window don't re-bill the upstream provider.

When an API key is missing the tool degrades gracefully: it returns
`{"error": "...", "data": []}` instead of raising — so the investigator
loop keeps going.
"""

from biq.tools.external.cache import cached_query, get_cached, store_cached  # noqa: F401
from biq.tools.external.market import market_snapshot  # noqa: F401
from biq.tools.external.news import news_search  # noqa: F401
from biq.tools.external.trends import trends_query  # noqa: F401
from biq.tools.external.web_search import web_search  # noqa: F401
