"""Semantic Scholar paper collector."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Optional

from ..storage.models import Author, Paper, PaperSource, PaperStatus
from .base import BaseCollector


class SemanticScholarCollector(BaseCollector):
    """Semantic Scholar paper collector."""

    source = PaperSource.SEMANTIC_SCHOLOLAR

    API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    REQUEST_DELAY = 1.5  # Conservative rate limiting
    _last_request_time: float = 0.0

    def __init__(
        self,
        fields: Optional[list[str]] = None,
        max_papers: int = 50,
        api_key: str = "",
    ):
        """Initialize Semantic Scholar collector.

        Args:
            fields: Research fields to search
            max_papers: Maximum papers per collection
            api_key: Optional API key for higher rate limits
        """
        self.fields = fields or ["Artificial Intelligence", "Machine Learning"]
        self.max_papers = max_papers
        self.api_key = api_key

    def collect(self, **kwargs) -> list[Paper]:
        """Collect papers from Semantic Scholar."""
        papers = []

        for field in self.fields:
            try:
                field_papers = self._search_by_field(field)
                papers.extend(field_papers)
                self._rate_limit()
            except Exception as e:
                print(f"Error collecting from Semantic Scholar ({field}): {e}")
                continue

        # Deduplicate
        seen = set()
        unique_papers = []
        for paper in papers:
            if paper.paper_id not in seen:
                seen.add(paper.paper_id)
                unique_papers.append(paper)

        return unique_papers[:self.max_papers]

    def get_recent(self, days: int = 1, **kwargs) -> list[Paper]:
        """Get recent papers (limited by API capabilities)."""
        # Semantic Scholar doesn't have great date filtering
        # We collect and filter by year
        papers = self.collect(**kwargs)

        current_year = datetime.now().year
        recent_papers = [p for p in papers if p.year >= current_year]

        return recent_papers[:self.max_papers]

    def _search_by_field(self, field: str, limit: int = 30) -> list[Paper]:
        """Search papers by research field."""
        return self._search(field, limit)

    def _search(self, query: str, limit: int = 30) -> list[Paper]:
        """Execute Semantic Scholar API search."""
        self._rate_limit()

        fields = "paperId,title,abstract,year,venue,citationCount,authors,externalIds,url,publicationDate"
        params = {
            "query": query,
            "limit": limit,
            "fields": fields,
        }

        url = f"{self.API_URL}?{urllib.parse.urlencode(params)}"

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            return self._parse_response(data)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("Semantic Scholar rate limited")
            else:
                print(f"Semantic Scholar HTTP error: {e.code}")
            return []
        except Exception as e:
            print(f"Semantic Scholar API error: {e}")
            return []

    def _parse_response(self, data: dict[str, Any]) -> list[Paper]:
        """Parse Semantic Scholar API response."""
        papers = []

        for item in data.get("data", []):
            paper = self._parse_paper(item)
            if paper:
                papers.append(paper)

        return papers

    def _parse_paper(self, item: dict[str, Any]) -> Optional[Paper]:
        """Parse a single paper from API response."""
        try:
            paper_id = item.get("paperId", "")
            if not paper_id:
                return None

            # External IDs
            ext_ids = item.get("externalIds") or {}
            arxiv_id = ext_ids.get("ArXiv", "")
            doi = ext_ids.get("DOI", "")

            # Authors
            authors = []
            for author in item.get("authors", []):
                name = author.get("name", "")
                if name:
                    authors.append(Author(name=name))

            # Publication date
            pub_date = item.get("publicationDate")
            published_date = None
            year = 0
            if pub_date:
                try:
                    published_date = datetime.fromisoformat(pub_date)
                    year = published_date.year
                except:
                    pass

            if year == 0:
                year = item.get("year", 0) or 0

            # Build paper ID
            if arxiv_id:
                paper_id = f"arxiv-{arxiv_id}"
            else:
                paper_id = f"s2-{paper_id}"

            return Paper(
                paper_id=paper_id,
                title=item.get("title", ""),
                authors=authors,
                abstract=item.get("abstract", "") or "",
                year=year,
                venue=item.get("venue", "") or "",
                citation_count=item.get("citationCount", 0) or 0,
                doi=doi,
                arxiv_id=arxiv_id,
                url=item.get("url", "") or "",
                source=self.source,
                status=PaperStatus.NEW,
                published_date=published_date,
            )

        except Exception as e:
            print(f"Error parsing Semantic Scholar paper: {e}")
            return None

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()