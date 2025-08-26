import os
import logging
from typing import Any, Dict, List, Optional

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency until installed
    TavilyClient = None  # type: ignore

logger = logging.getLogger("voice-agent.tavily")


class TavilySearch:
    """Thin wrapper around Tavily's search API.

    Reads TAVILY_API_KEY from env. Exposes a simple .search(query) that returns
    a compact JSON-friendly summary suitable to feed back to the LLM as a tool response.
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY is not set")
        if TavilyClient is None:
            raise RuntimeError("tavily-python not installed. Add 'tavily-python' to requirements.txt")
        self.client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Perform a web search and return a compact structured result.

        - query: user query string
        - max_results: cap number of result items (1-10)

        Returns a dict like {"answer": str | None, "results": [{"title","url","content"}], "query": str}
        """
        max_results = max(1, min(int(max_results or 5), 10))
        try:
            res = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
            )
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return {
                "query": query,
                "answer": None,
                "results": [],
                "error": str(e),
            }

        # Normalize shape
        results: List[Dict[str, Any]] = []
        for item in (res.get("results") or [])[:max_results]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                }
            )

        return {
            "query": query,
            "answer": res.get("answer"),
            "results": results,
        }
