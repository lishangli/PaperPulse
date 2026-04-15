"""arXiv paper collector with LaTeX source download support."""

from __future__ import annotations

import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

from ..storage.models import Author, Paper, PaperSource, PaperStatus
from .base import BaseCollector


class ArxivCollector(BaseCollector):
    """arXiv paper collector."""

    source = PaperSource.ARXIV

    # arXiv API base URL
    API_URL = "http://export.arxiv.org/api/query"
    # LaTeX source URL
    LATEX_URL = "https://arxiv.org/e-print/{arxiv_id}"

    # Rate limiting (default, can be overridden by config)
    _request_delay: float = 3.0  # arXiv requires >=3 seconds between requests
    _retry_count: int = 3
    _retry_wait: float = 5.0
    _last_request_time: float = 0.0

    def __init__(
        self,
        categories: Optional[list[str]] = None,
        keywords: Optional[list[str]] = None,
        max_papers: int = 100,
        arxiv_api_config: Optional[Any] = None,  # ArxivAPIConfig from config.py
    ):
        """Initialize arXiv collector.

        Args:
            categories: arXiv categories to monitor (e.g., cs.AI, cs.CL)
            keywords: Optional keywords to filter
            max_papers: Maximum papers per collection
            arxiv_api_config: ArxivAPIConfig object with rate limiting settings
        """
        self.categories = categories or ["cs.AI", "cs.CL", "cs.LG"]
        self.keywords = keywords or []
        self.max_papers = max_papers
        
        # Use config values if available
        if arxiv_api_config:
            self._request_delay = arxiv_api_config.rate_limit_wait
            self._retry_count = arxiv_api_config.retry_count
            self._retry_wait = arxiv_api_config.retry_wait

    def collect(self, **kwargs) -> list[Paper]:
        """Collect papers from arXiv based on categories."""
        papers = []

        for category in self.categories:
            try:
                cat_papers = self._search_by_category(category)
                papers.extend(cat_papers)
                self._rate_limit()
            except Exception as e:
                print(f"Error collecting from {category}: {e}")
                continue

        # Deduplicate by arxiv_id
        seen = set()
        unique_papers = []
        for paper in papers:
            if paper.arxiv_id and paper.arxiv_id not in seen:
                seen.add(paper.arxiv_id)
                unique_papers.append(paper)

        return unique_papers[:self.max_papers]

    def get_recent(self, days: int = 1, **kwargs) -> list[Paper]:
        """Get papers submitted in recent days."""
        papers = []

        for category in self.categories:
            try:
                cat_papers = self._search_recent(category, days=days)
                papers.extend(cat_papers)
                self._rate_limit()
            except Exception as e:
                print(f"Error collecting recent from {category}: {e}")
                continue

        # Deduplicate
        seen = set()
        unique_papers = []
        for paper in papers:
            if paper.arxiv_id and paper.arxiv_id not in seen:
                seen.add(paper.arxiv_id)
                unique_papers.append(paper)

        return unique_papers[:self.max_papers]

    def _search_by_category(self, category: str, limit: int = 50) -> list[Paper]:
        """Search papers by category."""
        query = f"cat:{category}"
        return self._search(query, limit)

    def _search_recent(self, category: str, days: int = 1, limit: int = 50) -> list[Paper]:
        """Search recent papers in a category."""
        # arXiv doesn't support date filtering in API, so we get recent and filter
        query = f"cat:{category}"
        papers = self._search(query, limit)

        # Filter by submission date
        cutoff = datetime.now() - timedelta(days=days)
        recent_papers = []

        for paper in papers:
            if paper.published_date and paper.published_date >= cutoff:
                recent_papers.append(paper)

        return recent_papers

    def _search(self, query: str, limit: int = 50) -> list[Paper]:
        """Execute arXiv API search."""
        self._rate_limit()

        params = {
            "search_query": query,
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        url = f"{self.API_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PaperPulse/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                xml_data = response.read().decode("utf-8")

            return self._parse_feed(xml_data)
        except urllib.error.HTTPError as e:
            print(f"arXiv API HTTP error: {e.code}")
            return []
        except urllib.error.URLError as e:
            print(f"arXiv API URL error: {e.reason}")
            return []
        except Exception as e:
            print(f"arXiv API error: {e}")
            return []

    def _parse_feed(self, xml_data: str) -> list[Paper]:
        """Parse arXiv Atom feed XML."""
        papers = []

        try:
            root = ElementTree.fromstring(xml_data)
        except ElementTree.ParseError:
            return []

        # Define namespaces
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }

        for entry in root.findall("atom:entry", ns):
            paper = self._parse_entry(entry, ns)
            if paper:
                papers.append(paper)

        return papers

    def _parse_entry(self, entry: ElementTree.Element, ns: dict) -> Optional[Paper]:
        """Parse a single entry from arXiv feed."""
        try:
            # Extract arXiv ID from URL
            id_url = entry.find("atom:id", ns)
            if id_url is None:
                return None

            arxiv_id = id_url.text.split("/")[-1] if id_url.text else ""
            if not arxiv_id:
                return None

            # Title
            title_elem = entry.find("atom:title", ns)
            title = self._clean_text(title_elem.text) if title_elem is not None else ""

            # Abstract
            summary_elem = entry.find("atom:summary", ns)
            abstract = self._clean_text(summary_elem.text) if summary_elem is not None else ""

            # Authors
            authors = []
            for author_elem in entry.findall("atom:author", ns):
                name_elem = author_elem.find("atom:name", ns)
                if name_elem is not None and name_elem.text:
                    authors.append(Author(name=name_elem.text))

            # Published date
            published_elem = entry.find("atom:published", ns)
            published_date = None
            if published_elem is not None and published_elem.text:
                published_date = self._parse_date(published_elem.text[:10])

            # Updated date
            updated_elem = entry.find("atom:updated", ns)
            if updated_elem is not None and updated_elem.text:
                year = int(updated_elem.text[:4])
            else:
                year = published_date.year if published_date else 0

            # Categories
            categories = []
            for cat_elem in entry.findall("atom:category", ns):
                term = cat_elem.get("term")
                if term:
                    categories.append(term)

            # Primary category as venue
            primary_cat = entry.find("arxiv:primary_category", ns)
            venue = primary_cat.get("term") if primary_cat is not None else ""

            # DOI
            doi_elem = entry.find("arxiv:doi", ns)
            doi = doi_elem.text if doi_elem is not None else ""

            return Paper(
                paper_id=f"arxiv-{arxiv_id}",
                title=title,
                authors=authors,
                abstract=abstract,
                year=year,
                venue=venue,
                citation_count=0,
                doi=doi,
                arxiv_id=arxiv_id,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                source=self.source,
                status=PaperStatus.NEW,
                published_date=published_date,
            )

        except Exception as e:
            print(f"Error parsing entry: {e}")
            return None

    def download_latex(self, arxiv_id: str, output_dir: Path) -> tuple[bool, str]:
        """Download LaTeX source from arXiv.

        Args:
            arxiv_id: arXiv paper ID
            output_dir: Directory to extract LaTeX source

        Returns:
            Tuple of (success, path or error message)
        """
        self._rate_limit()

        url = self.LATEX_URL.format(arxiv_id=arxiv_id)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Download tar.gz
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PaperPulse/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    tmp.write(response.read())
                tmp_path = tmp.name

            # Extract
            extract_dir = output_dir / arxiv_id.replace("/", "_")
            extract_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Clean up temp file
            Path(tmp_path).unlink()

            return True, str(extract_dir)

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "LaTeX source not available for this paper"
            return False, f"HTTP error {e.code}"
        except Exception as e:
            return False, f"Error downloading LaTeX: {e}"

    def download_pdf(self, arxiv_id: str, output_path: Path) -> tuple[bool, str]:
        """Download PDF from arXiv.

        Args:
            arxiv_id: arXiv paper ID
            output_path: Path to save PDF

        Returns:
            Tuple of (success, path or error message)
        """
        self._rate_limit()

        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PaperPulse/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                with open(output_path, "wb") as f:
                    f.write(response.read())

            return True, str(output_path)

        except urllib.error.HTTPError as e:
            return False, f"HTTP error {e.code}"
        except Exception as e:
            return False, f"Error downloading PDF: {e}"

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request_time = time.time()

    def get_paper_by_id(self, arxiv_id: str) -> Optional[Paper]:
        """Get a specific paper by arXiv ID."""
        query = f"id:{arxiv_id}"
        papers = self._search(query, limit=1)
        return papers[0] if papers else None