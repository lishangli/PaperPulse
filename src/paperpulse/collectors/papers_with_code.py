"""Papers with Code collector."""

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


class PapersWithCodeCollector(BaseCollector):
    """Papers with Code collector."""

    source = PaperSource.PAPERS_WITH_CODE

    API_URL = "https://paperswithcode.com/api/v1"
    REQUEST_DELAY = 1.0
    _last_request_time: float = 0.0

    def __init__(
        self,
        areas: Optional[list[str]] = None,
        max_papers: int = 50,
    ):
        """Initialize Papers with Code collector.

        Args:
            areas: Research areas (e.g., natural-language-processing, computer-vision)
            max_papers: Maximum papers per collection
        """
        self.areas = areas or ["natural-language-processing", "computer-vision"]
        self.max_papers = max_papers

    def collect(self, **kwargs) -> list[Paper]:
        """Collect papers from Papers with Code."""
        papers = []

        for area in self.areas:
            try:
                area_papers = self._get_area_papers(area)
                papers.extend(area_papers)
                self._rate_limit()
            except Exception as e:
                print(f"Error collecting from Papers with Code ({area}): {e}")
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
        """Get recent papers."""
        # Papers with Code API doesn't have great date filtering
        # We get latest papers from each area
        papers = self.collect(**kwargs)
        return papers[:self.max_papers]

    def _get_area_papers(self, area: str, limit: int = 30) -> list[Paper]:
        """Get papers from a specific area."""
        url = f"{self.API_URL}/areas/{area}/papers/"
        return self._fetch_papers(url, limit)

    def _get_latest_papers(self, limit: int = 30) -> list[Paper]:
        """Get latest papers across all areas."""
        url = f"{self.API_URL}/papers/"
        return self._fetch_papers(url, limit)

    def _fetch_papers(self, url: str, limit: int = 30) -> list[Paper]:
        """Fetch papers from URL."""
        self._rate_limit()

        params = {"page": 1, "items_per_page": limit}
        full_url = f"{url}?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(
                full_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "PaperPulse/1.0",
                }
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            return self._parse_response(data)

        except urllib.error.HTTPError as e:
            print(f"Papers with Code HTTP error: {e.code}")
            return []
        except Exception as e:
            print(f"Papers with Code API error: {e}")
            return []

    def _parse_response(self, data: dict[str, Any]) -> list[Paper]:
        """Parse API response."""
        papers = []

        for item in data.get("results", []):
            paper = self._parse_paper(item)
            if paper:
                papers.append(paper)

        return papers

    def _parse_paper(self, item: dict[str, Any]) -> Optional[Paper]:
        """Parse a single paper."""
        try:
            # Get arXiv ID if available
            arxiv_id = ""
            url_abs = item.get("url_abs", "") or ""
            if "arxiv.org/abs/" in url_abs:
                arxiv_id = url_abs.split("/abs/")[-1].split("/")[0]

            # Get paper ID
            paper_id = item.get("id", "")
            if arxiv_id:
                paper_id = f"arxiv-{arxiv_id}"
            elif paper_id:
                paper_id = f"pwc-{paper_id}"
            else:
                return None

            # Authors
            authors = []
            for author_name in item.get("authors", []):
                if author_name:
                    authors.append(Author(name=author_name))

            # Year
            published = item.get("date_published")
            year = 0
            published_date = None
            if published:
                try:
                    published_date = datetime.fromisoformat(published)
                    year = published_date.year
                except:
                    pass

            return Paper(
                paper_id=paper_id,
                title=item.get("title", ""),
                authors=authors,
                abstract=item.get("abstract", "") or "",
                year=year,
                venue="",  # Papers with Code doesn't provide venue
                citation_count=0,
                doi=item.get("doi", "") or "",
                arxiv_id=arxiv_id,
                url=url_abs or item.get("url_pdf", "") or "",
                source=self.source,
                status=PaperStatus.NEW,
                published_date=published_date,
            )

        except Exception as e:
            print(f"Error parsing Papers with Code paper: {e}")
            return None

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()